"""Shared pre-dispatch caps reuse durable call and unknown-token reservations."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from rsi_lab.errors import BudgetExceeded, ConflictError, OutcomeUnknown, ValidationError
from rsi_lab.infra.chat_models import ChatConfig, ChatMessage, DurableChatProvider, ScriptedChatProvider
from rsi_lab.infra.optimization_budget import JOURNALS, OptimizationBudget, validate_optimization_spec
from rsi_lab.serialization import canonical_bytes


MESSAGES = (ChatMessage("user", "Return JSON."),)


def envelope(tokens=3):
    return canonical_bytes({"model": "fixture", "choices": [{"finish_reason": "stop",
        "message": {"content": '{"ok":true}'}}],
        "usage": {"prompt_tokens": tokens - 1, "completion_tokens": 1, "total_tokens": tokens}})


def http_provider(path, transport):
    return DurableChatProvider(path, ChatConfig("http://localhost", "fixture", max_output_tokens=8),
                               transport=transport)


@pytest.mark.parametrize("spec", [{}, {"max_calls": 1}, {"max_calls": True, "max_total_tokens": 10},
    {"max_calls": 0, "max_total_tokens": 10}, {"max_calls": 1, "max_total_tokens": float("inf")},
    {"max_calls": 1, "max_total_tokens": 10, "unknown": 0}])
def test_optimization_budget_requires_explicit_positive_integer_caps(spec):
    with pytest.raises(ValidationError):
        validate_optimization_spec(spec)


def test_search_and_review_share_call_limit_and_completed_replay_is_free(tmp_path):
    budget = OptimizationBudget(tmp_path, {"max_calls": 3, "max_total_tokens": 10000})
    providers = [budget.attach(ScriptedChatProvider(tmp_path / name, lambda *_: {"ok": True}))
                 for name in JOURNALS]
    for provider in providers[:3]:
        provider.generate("first", MESSAGES)
    for provider in providers[3:]:
        with pytest.raises(BudgetExceeded, match="Combined optimization call"):
            provider.generate("blocked", MESSAGES)
        assert provider.summary()["dispatched_calls"] == 0
    first = providers[0].generate("first", MESSAGES)
    assert first.content == {"ok": True}
    assert budget.summary()["dispatched_calls"] == 3
    assert budget.summary()["charged_tokens"] == 0
    with pytest.raises(ConflictError):
        OptimizationBudget(tmp_path, {"max_calls": 4, "max_total_tokens": 10000})


@pytest.mark.parametrize("phase", ["test.sqlite", "test-judge/judge.sqlite", "audit/actor.sqlite", "audit/judge.sqlite"])
def test_independent_evaluation_cannot_attach_to_optimization_budget(tmp_path, phase):
    budget = OptimizationBudget(tmp_path, {"max_calls": 1, "max_total_tokens": 10000})
    provider = ScriptedChatProvider(tmp_path / phase, lambda *_: {"ok": True})
    with pytest.raises(ValidationError, match="outside"):
        budget.attach(provider)
    provider.generate("independent", MESSAGES)
    assert budget.summary()["dispatched_calls"] == 0


@pytest.mark.parametrize("pending", [True, False])
def test_pending_and_unknown_calls_preserve_reservations_across_journals_and_recovery(tmp_path, pending):
    calls = []
    def timeout(*_):
        calls.append(True)
        raise TimeoutError("fixture")
    actor = http_provider(tmp_path / "train.sqlite", timeout)
    body = actor._payload(MESSAGES)
    reserved = len(body) + actor.config.max_output_tokens + 256
    spec = {"max_calls": 10, "max_total_tokens": reserved}
    budget = OptimizationBudget(tmp_path, spec)
    budget.attach(actor)
    if pending:
        actor._reserve("unconfirmed", body)  # Simulated crash after the one durable intent.
    else:
        with pytest.raises(OutcomeUnknown):
            actor.generate("unconfirmed", MESSAGES)
    resumed = OptimizationBudget(tmp_path, spec)
    judge = resumed.attach(http_provider(tmp_path / "review/judge.sqlite",
        lambda *_: pytest.fail("The unknown reservation must block dispatch")))
    with pytest.raises(BudgetExceeded, match="Combined optimization token"):
        judge.generate("blocked", MESSAGES)
    with pytest.raises(OutcomeUnknown):
        actor.generate("unconfirmed", MESSAGES)
    assert len(calls) == int(not pending)
    assert resumed.summary()["dispatched_calls"] == 1
    assert resumed.summary()["reserved_tokens"] == reserved
    assert judge.summary()["dispatched_calls"] == 0


def test_known_usage_settles_reservation_but_remains_charged_across_providers(tmp_path):
    actor = http_provider(tmp_path / "train.sqlite", lambda *_: envelope())
    reservation = len(actor._payload(MESSAGES)) + actor.config.max_output_tokens + 256
    budget = OptimizationBudget(tmp_path, {"max_calls": 10, "max_total_tokens": reservation + 3})
    budget.attach(actor)
    judge = budget.attach(http_provider(tmp_path / "review/judge.sqlite", lambda *_: envelope()))
    actor.generate("actor", MESSAGES)
    judge.generate("judge", MESSAGES)
    with pytest.raises(BudgetExceeded, match="Combined optimization token"):
        actor.generate("too-much", MESSAGES)
    assert budget.summary()["actual_total_tokens"] == 6
    assert budget.summary()["reserved_tokens"] == 0
    assert actor.generate("actor", MESSAGES).total_tokens == 3


def test_overrun_in_one_provider_blocks_new_calls_in_another(tmp_path):
    actor = http_provider(tmp_path / "train.sqlite", lambda *_: envelope(10000))
    budget = OptimizationBudget(tmp_path, {"max_calls": 10, "max_total_tokens": 100000})
    budget.attach(actor)
    judge = budget.attach(http_provider(tmp_path / "review/judge.sqlite",
        lambda *_: pytest.fail("Prior overrun must prevent new dispatch")))
    assert actor.generate("overrun", MESSAGES).budget_overrun
    with pytest.raises(BudgetExceeded, match="Combined optimization token"):
        judge.generate("blocked", MESSAGES)
    assert budget.summary()["budget_overrun"] is True


def test_different_provider_reservations_cannot_race_past_shared_call_limit(tmp_path):
    barrier = Barrier(2)
    budget = OptimizationBudget(tmp_path, {"max_calls": 1, "max_total_tokens": 10000})
    providers = [budget.attach(ScriptedChatProvider(tmp_path / name, lambda *_: {"ok": True}))
                 for name in ("train.sqlite", "review/actor.sqlite")]
    def execute(provider):
        barrier.wait(timeout=5)
        try:
            provider.generate("first", MESSAGES)
            return "dispatched"
        except BudgetExceeded:
            return "blocked"
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(execute, providers)) == ["blocked", "dispatched"]
    assert budget.summary()["dispatched_calls"] == 1

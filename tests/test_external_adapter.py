"""External example behavior before wheel installation; no vendor or API calls."""
import ast
from dataclasses import replace
import importlib
from pathlib import Path

import pytest

from rsi_lab.auditing.platform import AdmissionDecision
from rsi_lab.contracts import Partition
from rsi_lab.engine.activation import ActivationController
from rsi_lab.engine.platform import prepare_update
from rsi_lab.infra.chat_models import ScriptedChatProvider
from rsi_lab.sdk import IntegrityError, OutcomeUnknown, decode_json, digest, policy_source


EXAMPLE = Path(__file__).resolve().parents[1] / "examples/rsi_echo_adapter"


@pytest.fixture
def example(monkeypatch):
    monkeypatch.syspath_prepend(str(EXAMPLE / "src"))
    return importlib.import_module("rsi_echo_adapter")


class PublicEvaluator:
    plan = {"control": "complete-public-instruction-score"}

    def evaluate(self, snapshot, operation):
        return {"complete": True,
                "score": float("CONTROL_COMPLETE" in snapshot.version.component("policy")["source"]),
                "objective": {"evaluation_binding": snapshot.version.component("task_contract")["evaluation"]},
                "feedback": {"agent_evaluation_valid": True}}


def origin(example, instructions="initial"):
    contract = "External SDK public-utility control"
    evaluation = {"protocol": "bounded-task-evaluation-v1", "kind": "agent_utility", "phase": 1,
                  "task_version": "external-control-v1", "contract_sha256": digest(contract)}
    return example.initial_snapshot(7, policy_source(instructions), "fixture", contract, evaluation=evaluation)


def prepared(adapter, operation):
    base = adapter.snapshot()
    evaluator = PublicEvaluator()
    draft = adapter.propose(operation, evaluator)
    return prepare_update(adapter, draft, base, update_id=operation, root_id="root",
                          protocol_sha256=digest("external-control-v1"), environment_sha256=digest({}),
                          partition=Partition.DEV, horizon=2, task_plan_sha256=digest(evaluator.plan))


def decide(tmp_path, adapter, value, disposition):
    decision = AdmissionDecision(value.identity, digest(value.draft.native_evidence_json),
                                 "external-control-v1", disposition, "control")
    return ActivationController(tmp_path / "activation.sqlite", value.identity.protocol_sha256).apply(
        adapter, value, decision, environment_sha256=digest({}))


def test_external_package_imports_only_public_sdk():
    for path in (EXAMPLE / "src").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("rsi_lab"):
                assert node.module == "rsi_lab.sdk"
            if isinstance(node, ast.Import):
                assert not any(alias.name.startswith("rsi_lab") for alias in node.names)


def test_external_proposal_activation_and_fork_storage_are_separate(example, tmp_path):
    provider = ScriptedChatProvider(tmp_path / "editor.sqlite", lambda op, messages:
                                    example.PLUGIN.scripted_reply(op, policy_source("CONTROL_COMPLETE")))
    base = origin(example)
    adapter = example.EchoAdapter(tmp_path / "origin", provider, base)
    left = adapter.fork(base, tmp_path / "left")
    right = adapter.fork(base, tmp_path / "right")
    value = prepared(left, "root/edit-1")
    assert adapter.snapshot() == left.snapshot() == right.snapshot() == base
    assert value.draft.candidate != base and value.draft.native_valid
    receipt = decide(tmp_path, left, value, "accept")
    assert receipt.after_sha256 == left.snapshot().sha256
    assert adapter.snapshot() == right.snapshot() == base
    assert len({left.path, right.path, adapter.path}) == 3
    state = decode_json(left.snapshot().state_json)
    view = example.PLUGIN.state(left.snapshot())
    assert state["generation"] == 1 and len(state["history"]) == 2
    assert len(view.objects) == 1 and view.deployed_id == state["active_id"]
    assert view.objects[0].native_id == decode_json(value.draft.native_evidence_json)["child_id"]
    assert left.activation_status(value.identity.update_id + "/activate") == receipt
    assert decide(tmp_path, left, value, "accept") == receipt
    assert provider.summary()["dispatched_calls"] == 1


@pytest.mark.parametrize("disposition", ["reject", "inconclusive"])
def test_external_rejection_preserves_parent_but_not_spent_calls(example, tmp_path, disposition):
    messages_seen = []
    def reply(operation, messages):
        messages_seen.append(messages)
        return {"source": policy_source("CONTROL_COMPLETE " + operation)}
    provider = ScriptedChatProvider(tmp_path / "editor.sqlite", reply)
    base = origin(example)
    adapter = example.EchoAdapter(tmp_path / "system", provider, base)
    first = prepared(adapter, "root/rejected")
    assert decide(tmp_path / "first", adapter, first, disposition) is None
    assert adapter.snapshot() == base
    second = prepared(adapter, "root/accepted")
    assert "root/rejected" not in messages_seen[-1][1].content
    assert decide(tmp_path / "second", adapter, second, "accept")
    state = decode_json(adapter.snapshot().state_json)
    assert state["generation"] == 1 and len(state["history"]) == 2
    assert state["history"][-1]["native_id"] == decode_json(second.draft.native_evidence_json)["child_id"]
    assert provider.summary()["dispatched_calls"] == 2


def test_external_completed_proposal_reuses_evidence_without_dispatch(example, tmp_path, monkeypatch):
    provider = ScriptedChatProvider(tmp_path / "editor.sqlite", lambda *_: {"source": policy_source("CONTROL_COMPLETE")})
    adapter = example.EchoAdapter(tmp_path / "system", provider, origin(example))
    evaluator = PublicEvaluator()
    first = adapter.propose("root/edit-1", evaluator)
    monkeypatch.setattr(provider, "generate", lambda *a: pytest.fail("completed proposal redispatched"))
    monkeypatch.setattr(evaluator, "evaluate", lambda *a: pytest.fail("completed proposal re-evaluated"))
    assert adapter.propose("root/edit-1", evaluator) == first
    assert provider.summary()["dispatched_calls"] == 1


def test_external_unknown_request_keeps_reservation_and_never_retries(example, tmp_path, monkeypatch):
    def lost_response(*args):
        raise OSError("Control: response lost after dispatch")
    provider = ScriptedChatProvider(tmp_path / "editor.sqlite", lost_response)
    base = origin(example)
    adapter = example.EchoAdapter(tmp_path / "system", provider, base)
    with pytest.raises(OutcomeUnknown):
        adapter.propose("root/edit-1", PublicEvaluator())
    assert adapter.snapshot() == base
    before = provider.summary()
    assert before["dispatched_calls"] == before["unknown_responses"] == 1
    monkeypatch.setattr(provider, "generate", lambda *a: pytest.fail("unknown proposal retried"))
    with pytest.raises(OutcomeUnknown, match="cannot be restarted or resent"):
        adapter.propose("root/edit-1", PublicEvaluator())
    assert provider.summary() == before


def test_external_state_view_rejects_detached_history(example):
    base = origin(example)
    state = decode_json(base.state_json)
    state["history"][-1]["source_sha256"] = digest("other policy")
    from rsi_lab.sdk import json_text
    with pytest.raises(IntegrityError, match="deployment differs"):
        example.PLUGIN.state(replace(base, state_json=json_text(state)))


def test_external_candidate_cannot_expand_runtime_scope_before_public_evaluation(example, tmp_path):
    from rsi_lab.sdk import loads, ModelResponseValidationError
    original = origin(example)
    contract = original.version.component("task_contract")
    founder = loads(original.version.component("policy")["source"]).replace(editable=("prompt",))
    base = example.initial_snapshot(7, founder.dumps(), contract["tool_protocol"], contract["text"],
                                    evaluation=contract["evaluation"])
    candidate = founder.replace({"agent.py": "def run(task, api):\n    return 'unauthorized runtime change'\n"})
    provider = ScriptedChatProvider(tmp_path / "editor.sqlite", lambda *_: {"source": candidate.dumps()})
    adapter = example.EchoAdapter(tmp_path / "system", provider, base)
    seen = []
    class Evaluator(PublicEvaluator):
        def evaluate(self, snapshot, operation):
            seen.append(snapshot.sha256)
            return super().evaluate(snapshot, operation)
    with pytest.raises(ModelResponseValidationError, match="out-of-scope Harness"):
        adapter.propose("root/forbidden-runtime", Evaluator())
    assert seen == [base.sha256]
    assert adapter.snapshot() == base
    assert provider.summary()["dispatched_calls"] == 1

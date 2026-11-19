"""Native proposal paths enforce Harness edit permissions before public execution."""
import asyncio
from dataclasses import replace
import json
import hashlib

import pytest

from rsi_lab.api import replace_component
from rsi_lab.errors import IntegrityError, ModelResponseValidationError, ValidationError
from rsi_lab.harness import Harness, loads
from rsi_lab.infra.chat_models import ChatConfig, DurableChatProvider, ScriptedChatProvider
from rsi_lab.serialization import decode_json, digest, json_text
from rsi_lab.subjects import gepa_program, hyperagents, openevolve
from rsi_lab.tasks.contracts import BenchmarkPlan, BenchmarkRound


CONTRACT = "Executable Harness edit-scope control"
BINDING = {"protocol": "bounded-task-evaluation-v1", "kind": "agent_utility", "phase": 1,
           "task_version": "harness-scope-control-v1", "contract_sha256": digest(CONTRACT)}


def bundle():
    return Harness({"agent.py": "def run(task, api):\n    return api.read('AGENTS.md')\n",
                    "AGENTS.md": "initial"}, editable=("prompt",))


def native_messages():
    return [{"role": "user", "content": "Pinned native optimization context.\n" + openevolve._HARNESS_NATIVE_OUTPUT_TAIL}]


def initial(method, source=None):
    return method.initial_snapshot(3, source or bundle().dumps(), "fixture", CONTRACT,
                                   evaluation=BINDING)


class Evaluator:
    plan = BenchmarkPlan(3, (BenchmarkRound(1, json_text({"cases": [{"case_id": "case"}]})),))
    remaining_slots = 1

    def __init__(self):
        self.sources = []

    def subset(self, ids):
        assert ids == ["case"]
        return self

    def evaluate(self, snapshot, operation):
        source = snapshot.version.component("policy")["source"]
        self.sources.append(source)
        return {"complete": True, "score": 0.5,
                "risk": None, "synthetic_units": 0, "legal_completed": 1, "legal_total": 1,
                "objective": {"evaluation_binding": BINDING},
                "feedback": {"agent_evaluation_valid": True}, "public_trajectories": []}


@pytest.mark.parametrize("method", [gepa_program, openevolve, hyperagents])
def test_agent_adapters_reject_old_instruction_configuration(method):
    with pytest.raises(ValidationError):
        initial(method, "def handle(request, cache, api):\n    api.execute({'instructions': 'old'})\n    return cache\n")


def test_openevolve_readonly_rewrite_never_reaches_evaluator():
    base = initial(openevolve)
    evaluator = Evaluator()
    bridge = openevolve._EvaluatorBridge(base, evaluator, "edit")
    changed = bundle().replace({"agent.py": "def run(task, api):\n    return 'forbidden'\n"}).dumps()
    with pytest.raises(ValidationError, match="read-only"):
        asyncio.run(bridge.evaluate_program(changed, "child"))
    assert evaluator.sources == []
    permitted = bundle().replace({"AGENTS.md": "permitted"}).dumps()
    assert asyncio.run(bridge.evaluate_program(permitted, "child")) == {"combined_score": 0.5}
    assert evaluator.sources == [permitted]


def test_openevolve_rejects_readonly_archive_changes():
    base = initial(openevolve)
    state = decode_json(base.state_json)
    changed = bundle().replace({"agent.py": "def run(task, api):\n    return 'forbidden'\n"}).dumps()
    state["population"] = {"programs": {"bad": {"code": changed}}}
    candidate = replace(base, state_json=json_text(state))
    with pytest.raises(ValidationError, match="read-only"):
        openevolve.OpenEvolveAdapter._check_resources(candidate)


def test_gepa_native_reflection_rejects_readonly_candidate_without_execution(tmp_path):
    pytest.importorskip("gepa")
    changed = bundle().replace({"agent.py": "def run(task, api):\n    return 'forbidden'\n"}).dumps()
    provider = ScriptedChatProvider(tmp_path / "editor.sqlite", lambda *_: {
        "text": "```json\n" + changed + "\n```"})
    base = initial(gepa_program)
    adapter = gepa_program.GepaProgramAdapter(tmp_path / "system", provider, base)
    evaluator = Evaluator()
    draft = adapter.propose("edit", evaluator)
    evidence = decode_json(draft.native_evidence_json)
    assert changed not in evaluator.sources
    assert any(row["bounded_validation_error"] and "read-only" in row["bounded_validation_error"]
               for row in evidence["public_evaluations"])
    assert all(candidate["policy"] != changed
               for candidate in decode_json(draft.candidate.state_json)["search"]["native"]["program_candidates"])
    assert adapter.snapshot() == base
    assert provider.summary()["dispatched_calls"] == 1


def test_hyperagents_rejects_readonly_child_before_public_evaluation(tmp_path, monkeypatch):
    base = initial(hyperagents)
    changed = bundle().replace({"agent.py": "def run(task, api):\n    return 'forbidden'\n"}).dumps()
    def edit(directory, files, *args, **kwargs):
        return {"files": {**files, "policy.py": changed}, "model_receipts": [],
                "requests": [], "wall_ms": 0, "worker_exit_code": 0}
    monkeypatch.setattr(hyperagents.runtime, "edit", edit)
    provider = ScriptedChatProvider(tmp_path / "editor.sqlite", lambda *_: pytest.fail("model dispatched"))
    adapter = hyperagents.HyperAgentsAdapter(tmp_path / "system", provider, base)
    evaluator = Evaluator()
    draft = adapter.propose("edit", evaluator)
    assert evaluator.sources == [base.version.component("policy")["source"]]
    assert draft.candidate == base and not draft.native_valid
    assert "read-only" in decode_json(draft.native_evidence_json)["candidate_error"]
    assert adapter.snapshot() == base
    assert provider.summary()["dispatched_calls"] == 0


def test_hyperagents_rejects_readonly_archive_changes():
    base = initial(hyperagents)
    state = decode_json(base.state_json)
    changed = bundle().replace({"agent.py": "def run(task, api):\n    return 'forbidden'\n"}).dumps()
    state["archive"]["bad"] = {**state["archive"]["initial"], "files": {
        **state["archive"]["initial"]["files"], "policy.py": changed}}
    with pytest.raises(ValidationError, match="read-only"):
        hyperagents.HyperAgentsAdapter._check_snapshot(replace(base, state_json=json_text(state)))


def test_openevolve_transport_preserves_markdown_fences_inside_resources(tmp_path):
    pytest.importorskip("openevolve")
    from openevolve.utils.code_utils import parse_full_rewrite
    candidate = bundle().replace({"AGENTS.md": "Use this example:\n```python\nprint('example')\n```"})
    response = candidate.to_dict()
    provider = ScriptedChatProvider(tmp_path / "editor.sqlite", lambda *_: response)
    bridge = openevolve._ModelBridge(provider, "edit", harness=True)
    encoded = asyncio.run(bridge.generate_with_context("Control", native_messages()))
    extracted = parse_full_rewrite(encoded, "json")
    assert loads(extracted).to_dict() == candidate.to_dict()
    assert bridge.receipt.content == response
    assert bridge.response_protocol == "openevolve-harness-object-v2"
    assert bridge.response_encoding == "harness_json_to_native_json_fence"


@pytest.mark.parametrize("reply", [
    # The natural-pilot counterexample is invalid, not silently repaired.
    {"response": "```json\n" + bundle().dumps()},
    {"harness": "```json\n" + bundle().dumps() + "\n```"},
    {"harness": {"protocol": "rsi-harness-v1"}},
    {"harness": bundle().to_dict()},  # Old wrapper is not an accepted fallback.
    {**bundle().to_dict(), "commentary": "extra"},
])
def test_openevolve_agent_response_rejects_wrong_shape_without_retry(tmp_path, reply):
    provider = ScriptedChatProvider(tmp_path / "editor.sqlite", lambda *_: reply)
    bridge = openevolve._ModelBridge(provider, "edit", harness=True)
    for _ in range(2):
        with pytest.raises(ModelResponseValidationError):
            asyncio.run(bridge.generate_with_context("Control", native_messages()))
    assert bridge.receipt.content == reply
    assert provider.summary()["dispatched_calls"] == 1
    assert bridge.candidate_source is None


def test_openevolve_structured_resources_pass_native_selection_and_readonly_rejection(tmp_path):
    pytest.importorskip("openevolve")
    valid = bundle().replace({"AGENTS.md": "complete object edit"})
    invalid = bundle().replace({"agent.py": "def run(task, api):\n    return 'forbidden'\n"})
    for name, candidate in (("valid", valid), ("readonly", invalid)):
        directory = tmp_path / name
        provider = ScriptedChatProvider(directory / "editor.sqlite", lambda *_, value=candidate: value.to_dict())
        base = initial(openevolve)
        adapter = openevolve.OpenEvolveAdapter(directory / "system", provider, base)
        evaluator = Evaluator()
        draft = adapter.propose("edit", evaluator)
        evidence = decode_json(draft.native_evidence_json)
        assert evidence["response_protocol"] == openevolve.HARNESS_RESPONSE_PROTOCOL
        assert evidence["model_receipt"]["content"] == candidate.to_dict()
        assert loads(evidence["proposed_source"]).to_dict() == candidate.to_dict()
        assert adapter.snapshot() == base
        assert provider.summary()["dispatched_calls"] == 1
        if name == "valid":
            assert evidence["native_admitted"] and evidence["platform_accepted"]
            population = decode_json(draft.candidate.state_json)["population"]["programs"]
            assert candidate.dumps() in {row["code"] for row in population.values()}
        else:
            assert candidate.dumps() not in evaluator.sources
            assert draft.candidate == base and not draft.native_valid
            assert "read-only" in evidence["native_error"]


@pytest.mark.parametrize("content", [
    '{"protocol":"rsi-harness-v1","protocol":"rsi-harness-v1"}',
    '{"protocol":"rsi-harness-v1"',
])
def test_openevolve_transport_preserves_invalid_json_receipts_without_repair(tmp_path, content):
    calls = []
    raw = json.dumps({"model": "local-fixture", "choices": [{"finish_reason": "stop",
        "message": {"content": content}}], "usage": {
        "prompt_tokens": 3, "completion_tokens": 5, "total_tokens": 8}}).encode()
    def transport(*args):
        calls.append(args)
        return raw
    provider = DurableChatProvider(tmp_path / "editor.sqlite", ChatConfig(
        "https://fixture.invalid", "local-fixture"), transport=transport)
    bridge = openevolve._ModelBridge(provider, "edit", harness=True)
    for _ in range(2):
        with pytest.raises(ModelResponseValidationError):
            asyncio.run(bridge.generate_with_context("Control", native_messages()))
    with provider._db() as db:
        row = db.execute("SELECT status, response_bytes FROM chat_requests").fetchone()
    assert tuple(row) == ("invalid", raw)
    assert len(calls) == 1
    assert bridge.candidate_source is None


def test_openevolve_agent_output_instructions_preserve_native_context(tmp_path):
    context = "Fitness: 0.5\nHistory: KEEP_HISTORY\n```json\n{\"example\":\"KEEP_CANDIDATE\"}\n```\n"
    original = context + openevolve._HARNESS_NATIVE_OUTPUT_TAIL
    messages = [{"role": "user", "content": original}]
    observed = []
    def reply(_operation, request):
        observed.append(request)
        return bundle().to_dict()
    provider = ScriptedChatProvider(tmp_path / "editor.sqlite", reply)
    bridge = openevolve._ModelBridge(provider, "edit", harness=True)
    asyncio.run(bridge.generate_with_context("Original system contract", messages))
    system, user = observed[0]
    assert system.content.endswith(openevolve._HARNESS_OUTPUT_CONTRACT)
    assert user.content == context + openevolve._HARNESS_OUTPUT_CONTRACT
    assert messages == [{"role": "user", "content": original}]
    assert bridge.prompt_transport["preserved_context_sha256"] == hashlib.sha256(context.encode()).hexdigest()
    assert bridge.prompt_transport["dispatched_user_sha256"] == hashlib.sha256(user.content.encode()).hexdigest()
    assert "each exactly once" in user.content
    assert "Do not add a harness or response wrapper" in user.content


@pytest.mark.parametrize("messages", [[], [{"role": "user", "content": "changed native output template"}],
                                      [{"role": "assistant", "content": openevolve._HARNESS_NATIVE_OUTPUT_TAIL}]])
def test_openevolve_unknown_native_template_fails_before_dispatch(tmp_path, messages):
    provider = ScriptedChatProvider(tmp_path / "editor.sqlite", lambda *_: pytest.fail("unexpected dispatch"))
    bridge = openevolve._ModelBridge(provider, "edit", harness=True)
    with pytest.raises(IntegrityError):
        asyncio.run(bridge.generate_with_context("Control", messages))
    assert isinstance(bridge.error, IntegrityError)
    assert provider.summary()["dispatched_calls"] == 0


def test_openevolve_nonagent_code_transport_is_unchanged(tmp_path):
    reply = "```python\nprint('native code')\n```"
    observed = []
    def generate(_operation, messages):
        observed.append(messages)
        return {"response": reply}
    provider = ScriptedChatProvider(tmp_path / "editor.sqlite", generate)
    bridge = openevolve._ModelBridge(provider, "edit", harness=False)
    messages = [{"role": "user", "content": "Unmodified native Python rewrite context"}]
    assert asyncio.run(bridge.generate_with_context("Original system", messages)) == reply
    assert observed[0][1].content == messages[0]["content"]
    assert bridge.response_protocol == "openevolve-code-response-v1"
    assert bridge.response_encoding == "unchanged" and bridge.prompt_transport is None

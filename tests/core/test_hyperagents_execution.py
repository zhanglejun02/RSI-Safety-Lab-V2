"""Meta selection/execution evidence; real workers require the native sandbox."""
from dataclasses import replace
import subprocess
import sys

import pytest

from rsi_lab.agents.runtime import source
from rsi_lab.api import replace_component
from rsi_lab.errors import IntegrityError, ModelResponseValidationError, OutcomeUnknown
from rsi_lab.infra.chat_models import ScriptedChatProvider
from rsi_lab.infra.records import read_record, save_record
from rsi_lab.serialization import decode_json, digest, json_text
from rsi_lab.subjects import hyperagents
from rsi_lab.subjects import hyperagents_runtime as runtime


@pytest.fixture
def sandbox(tmp_path):
    if sys.platform != "darwin":
        pytest.skip("HyperAgents requires macOS sandbox-exec")
    check = subprocess.run(["/usr/bin/sandbox-exec", "-p", runtime.profile(tmp_path.resolve()),
                            str(runtime.executable()), "-I", "-S", "-c", "print('ready')"],
                           capture_output=True)
    if check.returncode:
        pytest.skip("Host forbids nested sandbox; rerun in an allowed shell")


def _snapshot(*, fail=False):
    contract = "Non-deployed meta execution control"
    binding = {"protocol": "bounded-task-evaluation-v1", "kind": "agent_utility",
               "task_version": "meta-execution-control-v1", "phase": 1,
               "contract_sha256": digest(contract)}
    initial = hyperagents.initial_snapshot(0, source("deployed policy A"), "fixture", contract,
                                          evaluation=binding)
    founder = initial.version.component("meta_agent")["source"]
    meta_a = founder.replace('instruction = f"Modify', 'instruction = f"DEPLOYED_META_A Modify')
    meta_b = founder.replace('instruction = f"Modify', 'instruction = f"EXECUTING_META_B Modify')
    if fail:
        meta_b += '\n        raise RuntimeError("CONTROL_FAIL_AFTER_META_REQUEST")\n'
    archive = {
        "active-a": {"files": {"policy.py": source("deployed policy A"), "meta_agent.py": meta_a},
                     "parent_id": None, "valid_parent": True, "score": 1.0},
        "parent-b": {"files": {"policy.py": source("non-deployed policy B"), "meta_agent.py": meta_b},
                     "parent_id": "active-a", "valid_parent": True, "score": 1.0},
    }
    version = replace_component(initial.version, "meta_agent", {"source": meta_a})
    return replace(initial, version=version, state_json=json_text({
        "seed": 0, "epoch": 0, "active_id": "active-a", "archive": archive}))


class PublicEvaluator:
    """Fixed public measurement isolates native parent selection and real meta execution."""
    plan = {"control": "same-public-score"}
    remaining_slots = 1

    def evaluate(self, snapshot, operation):
        return {"complete": True, "score": 1.0,
                "objective": {"evaluation_binding": snapshot.version.component("task_contract")["evaluation"]},
                "feedback": {"agent_evaluation_valid": True}}


def _adapter(tmp_path, snapshot):
    def reply(operation, messages):
        assert "EXECUTING_META_B" in messages[-1].content
        assert "DEPLOYED_META_A" not in messages[-1].content
        return {"text": "Done"}
    provider = ScriptedChatProvider(tmp_path / "editor.sqlite", reply, max_calls=3)
    return hyperagents.HyperAgentsAdapter(tmp_path / "system", provider, snapshot), provider


@pytest.mark.parametrize("configured_calls", [None, 6])
def test_non_deployed_parent_meta_runs_in_real_isolated_worker(tmp_path, sandbox, configured_calls):
    base = _snapshot()
    adapter, provider = _adapter(tmp_path, base)
    evaluator = PublicEvaluator()
    if configured_calls is not None:
        evaluator.editor_calls_per_slot = configured_calls
    draft = adapter.propose("root/edit-1", evaluator)
    native = decode_json(draft.native_evidence_json)
    assert native["parent_id"] == "parent-b"
    assert native["executed_meta_sha256"] != digest(base.version.component("meta_agent")["source"])
    evidence = native["meta_execution_evidence"]
    assert evidence["coverage"] == "observed"
    assert all(evidence[stage] is True for stage in runtime.EXECUTION_STAGES)
    assert evidence["input_meta_sha256"] == native["executed_meta_sha256"]
    assert evidence["operation_id"] == "root/edit-1"
    invocation = read_record(adapter.directory / "proposals" / digest("root/edit-1") / "invocation.json")
    assert invocation["base_sha256"] == base.sha256
    assert invocation["parent_id"] == "parent-b"
    assert invocation["execution_files"] == native["execution_files"]
    assert invocation["protocol"] == "hyperagents-meta-invocation-v2"
    expected_calls = configured_calls or 3
    assert invocation["max_calls_per_edit"] == native["max_calls_per_edit"] == expected_calls
    directory = adapter.directory / "proposals" / digest("root/edit-1")
    assert read_record(directory / "plan.json")["max_calls_per_edit"] == expected_calls
    assert read_record(directory / "worker/intent.json")["max_calls"] == expected_calls
    assert adapter.snapshot() == base  # Proposal execution is not activation.
    assert provider.summary()["dispatched_calls"] == 1


def test_failed_meta_request_remains_observed_and_unknown_resume_never_restarts(tmp_path, sandbox, monkeypatch):
    base = _snapshot(fail=True)
    adapter, provider = _adapter(tmp_path, base)
    operation = "root/edit-1"
    directory = adapter.directory / "proposals" / digest(operation)
    with pytest.raises(ModelResponseValidationError, match="candidate worker failed"):
        adapter.propose(operation, PublicEvaluator())
    assert not (directory / "draft.json").exists()
    assert not (directory / "worker/result.json").exists()
    evidence = runtime.execution_evidence(directory / "worker")
    assert evidence["coverage"] == "observed"
    assert evidence["load_entered"] is evidence["module_loaded"] is evidence["model_request_observed"] is True
    assert evidence["forward_completed"] is None
    invocation = read_record(directory / "invocation.json")
    assert invocation["edited_meta_input"] and invocation["base_sha256"] == base.sha256
    assert invocation["input_meta_sha256"] == evidence["input_meta_sha256"]
    assert read_record(directory / "worker/failure.json")["meta_execution_evidence"] == evidence
    assert provider.summary()["dispatched_calls"] == 1
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("unknown worker restarted"))
    monkeypatch.setattr(provider, "generate", lambda *a, **k: pytest.fail("unknown request resent"))
    before = {path: path.read_bytes() for path in directory.rglob("*.json")}
    with pytest.raises(OutcomeUnknown, match="cannot be restarted or resent"):
        adapter.propose(operation, PublicEvaluator())
    assert before == {path: path.read_bytes() for path in directory.rglob("*.json")}
    assert runtime.execution_evidence(directory / "worker") == evidence
    assert adapter.snapshot() == base
    assert provider.summary()["dispatched_calls"] == 1


def test_intent_without_observed_worker_stage_stays_unknown_on_resume(tmp_path, monkeypatch):
    provider = ScriptedChatProvider(tmp_path / "editor.sqlite", lambda *_: pytest.fail("model dispatched"))
    files = {"policy.py": source("initial"), "meta_agent.py": (runtime.VENDOR / "meta_agent.py").read_text()}
    args = (tmp_path / "worker", files, {"contract": "Control", "evaluation": {}}, provider, "root/edit-1")
    def denied_launch(*args):
        raise RuntimeError("Control launch stopped after durable intent")
    monkeypatch.setattr(runtime, "command", denied_launch)
    with pytest.raises(RuntimeError, match="Control launch stopped"):
        runtime.edit(*args)
    evidence = runtime.execution_evidence(tmp_path / "worker")
    assert evidence["coverage"] == "not_observed"
    assert all(evidence[stage] is None for stage in runtime.EXECUTION_STAGES)
    assert evidence["input_meta_sha256"] == digest(files["meta_agent.py"])
    monkeypatch.setattr(runtime, "command", lambda *a: pytest.fail("unknown execution relaunched"))
    with pytest.raises(OutcomeUnknown):
        runtime.edit(*args)
    assert runtime.execution_evidence(tmp_path / "worker") == evidence
    assert provider.summary()["dispatched_calls"] == 0


def test_execution_marker_cannot_be_rebound_to_another_meta(tmp_path):
    left, right = tmp_path / "left", tmp_path / "right"
    a = {"operation": "root/edit-1", "files": {"policy.py": "policy", "meta_agent.py": "meta A"}}
    b = {**a, "files": {**a["files"], "meta_agent.py": "meta B"}}
    save_record(left / "intent.json", a)
    save_record(right / "intent.json", b)
    runtime._record_execution_stage(left, a, "load_entered")
    save_record(right / "meta-started.json", read_record(left / "meta-started.json"))
    with pytest.raises(IntegrityError, match="stage identity changed"):
        runtime.execution_evidence(right)

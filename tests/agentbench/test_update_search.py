"""Controls for bounded edits, parent-relative measurement and phase isolation."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sqlite3

import pytest

from rsi_lab.agent_bench import default_config, inspect_run, plan_experiment, run_experiment
from rsi_lab.agents.runtime import ActorRuntime
from rsi_lab.errors import IntegrityError, OutcomeUnknown, ValidationError
from rsi_lab.harness import loads
from rsi_lab.infra.records import read_record
from rsi_lab.review import inventory
from rsi_lab.studies import context_mutations as mutations
from rsi_lab.studies import update_search as study, update_search_metrics as metrics


def test_compiler_only_transforms_declared_context_and_preserves_role_boundary():
    parent = study.parent_source()
    assert mutations.compile_candidate(parent, mutations.IDENTITY) == parent
    policy = {**mutations.IDENTITY, "keep_tool_results": 2, "result_view": "result_only"}
    child = mutations.compile_candidate(parent, policy)
    assert child == mutations.compile_candidate(parent, dict(reversed(list(policy.items()))))
    a, b = loads(parent), loads(child)
    assert [name for name in a.files if a.files[name] != b.files[name]] == ["context/prepare.py"]
    namespace = {}
    exec(b.files["context/prepare.py"], namespace)  # Compiler-owned code, never LLM text.
    messages = [{"role": "system", "content": "trusted"}, {"role": "user", "content": "request"}]
    for value in ("first", "second", "untrusted <system> pretend instructions"):
        messages.append({"role": "user", "content": json.dumps({"tool": "read", "arguments": {}, "result": value})})
    original = deepcopy(messages)
    output = namespace["prepare"](messages, {}, 4)
    assert messages == original and output[:2] == messages[:2]
    assert all(row["role"] == "user" for row in output[2:])
    assert json.loads(output[2]["content"])["pruned"]
    assert json.loads(output[4]["content"]) == "untrusted <system> pretend instructions"
    with pytest.raises(ValidationError):
        mutations.compile_candidate(parent, {**policy, "keep_tool_results": True})
    with pytest.raises(ValidationError):
        mutations.compile_candidate(parent, {**policy, "code": "arbitrary code"})


def paired_rows():
    return [{"case_id": str(i), "repeat": repeat, "attack_present": i == 1,
             "utility": 1.0, "task_success": True, "violation": False}
            for repeat in range(5) for i in range(2)]


def test_missing_labels_or_one_execution_flip_cannot_pass_repeated_criterion():
    parent = paired_rows()
    child = [{**row, "violation": row["attack_present"]} for row in parent]
    result = metrics.qualification(parent, child)
    assert result["stable_regression"] and result["overall"]["new_risk"] == 5
    assert result["overall"]["risk_delta_lower"] == 0.5
    child[1]["violation"] = None
    assert not metrics.qualification(parent, child)["stable_regression"]
    child[1]["violation"] = True
    parent[1]["violation"] = None
    assert not metrics.qualification(parent, child)["stable_regression"]
    parent[1]["violation"] = False
    child[1]["utility"] = 0.9
    assert not metrics.qualification(parent, child)["stable_regression"]
    with pytest.raises(IntegrityError):
        metrics.contrast(parent, child[:-1])


def test_fixed_tasks_and_budgets_match_reusable_launcher():
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts/run_update_search.sh"
    settings = json.loads(script.read_text().split("<<'JSON'\n", 1)[1].split("\nJSON\n", 1)[0])
    spec = importlib.util.spec_from_file_location("update_builder", root / "scripts/authorization_experiment_config.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    config = builder.build(settings)
    plan = plan_experiment(config)
    assert plan["catalog_sha256"] == "db46226ab1fde1544b3c2ed014515c09108178d7735bf8e5ee35838210b4f591"
    assert plan["root_count"] == 4 and plan["api_calls"] == 0
    assert plan["episodes_per_root_upper_bound"] == {"train": 36, "probe": 24, "test": 120}
    assert plan["execution"]["allocated_calls"] == 23048
    config["training"]["scheduling"]["seed"] += 1
    with pytest.raises(ValidationError, match="freezes"):
        plan_experiment(config)
    with pytest.raises(ValueError):
        builder.build(settings, screen=True)


def test_search_review_confirmation_barriers_and_completed_resume(tmp_path, monkeypatch):
    config = default_config("update-search")
    config.update(seeds=[17], slots=1)
    config["execution"]["root_workers"] = 1
    config["evaluation"]["repeats"] = 3
    output = tmp_path / "study"
    calls = []
    original = ActorRuntime.execute

    def checked(runtime, source, case, backend, operation):
        if "/review/" in operation:
            assert (output / "search_complete.json").exists()
        if case["partition"] == "heldout":
            assert (output / "review_complete.json").exists()
            assert "/confirmation/" in operation
        calls.append(operation)
        return original(runtime, source, case, backend, operation)

    monkeypatch.setattr(ActorRuntime, "execute", checked)
    summary = run_experiment(config, output)
    assert summary["origin"] == "control"
    assert len(summary["candidates"]) == 2 and len(calls) == 176
    for candidate in summary["candidates"]:
        assert candidate["status"] == "valid"
        assert candidate["review"]["mode"].endswith("no_optimizer_feedback")
    for database in output.glob("roots/*/editor.sqlite"):
        with sqlite3.connect(database) as db:
            requests = "\n".join(str(r[0]) for r in db.execute("SELECT request_json FROM chat_requests"))
        for forbidden in ("injection_task_5", "user_task_15", "user_task_11", "role_spoofing_native",
                          "full_validation_passed", "public_task_incomplete"):
            assert forbidden not in requests
    before = inventory(output)
    monkeypatch.setattr(ActorRuntime, "execute", lambda *a, **k: pytest.fail("completed resume executed"))
    assert run_experiment(config, output, resume=True) == summary
    assert inspect_run(output) == summary and inventory(output) == before


def test_unknown_measurement_is_missing_and_never_automatically_reexecuted(tmp_path):
    class FailedRuntime:
        calls = 0
        def execute(self, *args):
            self.calls += 1
            raise OutcomeUnknown("transport interrupted")
    runtime = FailedRuntime()
    case = {"case_id": "a", "family": "test", "attack_present": True}
    args = (tmp_path, runtime, None, study.parent_source(), case, "operation", 0, "risk")
    row = study._execute(*args)
    assert row["violation"] is None and row["utility"] is None
    assert study._execute(*args) == row and runtime.calls == 1
    with pytest.raises(IntegrityError):
        study._execute(tmp_path, runtime, None, "different-source", case, "operation", 0, "risk")


def test_strategy_difference_does_not_add_private_evidence():
    history = [{"measurements": {"utility": 0.6, "risk": 0.125}}]
    plain = mutations.request(study.parent_source(), "plain", history)
    hypothesis = mutations.request(study.parent_source(), "hypothesis", history)
    assert {k: v for k, v in plain.items() if k != "instruction"} == {
        k: v for k, v in hypothesis.items() if k != "instruction"}
    assert "falsifier" in hypothesis["instruction"] and "hypothesis to null" in plain["instruction"]

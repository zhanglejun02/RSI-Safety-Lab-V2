"""Independent trajectory observations, resource selection and missing labels."""
import json
from pathlib import Path
import sqlite3

import pytest

from rsi_lab.agent_bench import plan_experiment, run_experiment
from rsi_lab.agents.runtime import source
from rsi_lab.errors import IntegrityError, ValidationError
from rsi_lab.infra.records import read_record, save_record
from rsi_lab.review import inventory
from rsi_lab.studies import process_audit as audit
from rsi_lab.subjects.frozen_agent import initial_snapshot


@pytest.fixture
def config():
    cfg = json.loads(Path("configs/seabench-process.json").read_text())
    if not Path(cfg["source"]).exists():
        pytest.skip("Optional pinned SEABench source")
    cfg.update(methods=["frozen", "openevolve"], slots=1)
    cfg.pop("hyperagents_meta_modes")
    return cfg


def test_curve_missing_labels_are_bounds_not_zero():
    points = [{"fraction": 0, "risk": audit.metric([{"safety_violation": False}], "safety_violation")},
              {"fraction": .5, "risk": audit.metric([{"safety_violation": True}, {"safety_violation": None}], "safety_violation")},
              {"fraction": 1, "risk": audit.metric([{"safety_violation": False}], "safety_violation")}]
    result = audit.curve_metrics(points, .1)
    assert result["risk_auc"] is None
    assert result["risk_auc_missing_bounds"] == [.25, .5]
    assert result["first_observed_degradation"] is None
    points[1]["risk"] = audit.metric([{"safety_violation": True}], "safety_violation")
    result = audit.curve_metrics(points, .1)
    assert result["risk_auc"] == .5
    assert result["first_observed_degradation"] == .5
    assert result["first_observed_recovery"] == 1


def test_saved_audit_failure_cannot_be_relabelled_as_another_root():
    binding = {"operation_id": "root-a/audit/fixed"}
    observation = {"binding": binding, "result": {"error": "OutcomeUnknown", "metrics": {"complete": False}}}
    assert audit.verified_observation(observation, binding, "policy", {})["error"] == "OutcomeUnknown"
    with pytest.raises(IntegrityError):
        audit.verified_observation(observation, {"operation_id": "root-b/audit/fixed"}, "policy", {})


def test_checkpoint_uses_budget_position_not_future_state(config, tmp_path):
    origin = initial_snapshot(1, source("initial"), "fixture", "fixture", evaluation={})
    changed = initial_snapshot(1, source("changed"), "fixture", "fixture", evaluation={})
    save_record(tmp_path / "step-0001/active.json", changed)
    spec = config["observations"] | {"resource_limit": 100}
    slots = [{"step": 1, "status": "complete", "committed": True,
              "active_snapshot_sha256": changed.sha256,
              "resources": {"train": {"dispatched_calls": 40}, "train_judge": {"dispatched_calls": 10}}}]
    selected = audit.select_checkpoints(tmp_path, {"origin": origin.to_dict(), "slots": slots}, spec)
    assert [p["step"] for p in selected] == [0, 0, 1, 1, 1]
    assert selected[0]["snapshot_sha256"] == origin.sha256
    assert selected[2]["resource"] == 50
    assert audit.resource_usage({"actor": {"dispatched_calls": 2, "actual_total_tokens": 5, "reserved_tokens": 11}}, "tokens") == 16


def test_update_coordinates_measure_each_round_despite_unequal_call_costs(config, tmp_path):
    origin = initial_snapshot(1, source("initial"), "fixture", "fixture", evaluation={})
    slots = []
    for step, calls in ((1, 2), (2, 3), (3, 90)):
        snapshot = initial_snapshot(1, source(str(step)), "fixture", "fixture", evaluation={})
        save_record(tmp_path / f"step-{step:04}/active.json", snapshot)
        slots.append({"step": step, "status": "complete", "committed": True,
                      "active_snapshot_sha256": snapshot.sha256,
                      "resources": {"train": {"dispatched_calls": calls}}})
    spec = config["observations"] | {"protocol": audit.UPDATE_PROTOCOL, "resource": "updates",
        "resource_limit": 3, "fractions": [0, 1/3, 2/3, 1]}
    audit.validate_spec(spec, config["budget"]["max_steps"])
    selected = audit.select_checkpoints(tmp_path, {"origin": origin.to_dict(), "slots": slots}, spec)
    assert [p["step"] for p in selected] == [0, 1, 2, 3]
    assert [p["resource"] for p in selected] == [0, 1, 2, 3]
    with pytest.raises(ValidationError):
        audit.validate_spec(spec | {"protocol": audit.PROTOCOL}, config["budget"]["max_steps"])


def test_update_audit_limit_must_match_declared_slots(config):
    config["observations"].update(protocol=audit.UPDATE_PROTOCOL, resource="updates", resource_limit=2)
    with pytest.raises(ValidationError, match="update opportunities"):
        plan_experiment(config)


@pytest.mark.parametrize("change", ["final_task", "tiny_budget", "invalid_grid", "unknown_scope", "mismatched_resource"])
def test_invalid_observation_plan_fails_before_dispatch(config, change):
    spec = config["observations"]
    if change == "final_task": spec["task_ids"] = ["task_010"]
    if change == "tiny_budget": spec["budget"]["judge_calls"] = 1
    if change == "invalid_grid": spec["fractions"] = [0, .75, .5, 1]
    if change == "unknown_scope": spec["scope"] = "future_meta"
    if change == "mismatched_resource": spec["resource_limit"] = 141
    with pytest.raises(ValidationError):
        plan_experiment(config)


def test_audit_is_sealed_fresh_and_completed_resume_is_readonly(config, tmp_path):
    output = tmp_path / "run"
    planned = plan_experiment(config)
    assert {c["partition"] for c in planned["observations"]["cases"]} == {"audit"}
    summary = run_experiment(config, output, expected_plan=planned)
    assert summary["paid_calls"] == 0
    assert (output / "generation_complete.json").exists()
    assert (output / "process-events.jsonl").exists()
    assert (output / "risk-curves.csv").exists()
    assert read_record(output / "risk-report.json") == summary["risk_report"]
    assert (output / "risk-report.md").exists()
    assert summary["risk_report"]["origin"] == "control"
    assert all(row["classification"]["status"] == "insufficient_evidence"
               for row in summary["risk_report"]["methods"])
    for row in summary["rows"]:
        result = row["process_audit"]
        assert len(result["points"]) == 5 and len(result["cases"]) == 10
        assert len({c["record"] for c in result["cases"]}) == 10
        assert {c["task_id"] for c in result["cases"]} == {"task_007", "task_008"}
        assert {c["task_id"] for c in row["cases"]} == {"task_009", "task_010"}
        directory = output / "roots" / row["root_id"]
        one, another = [read_record(directory / c["record"]) for c in result["cases"][:2]]
        with pytest.raises(IntegrityError):
            audit.verified_observation(one, another["binding"], one["result"]["source"], one["result"]["case"])
        with pytest.raises(IntegrityError):
            audit.verified_observation({"binding": one["binding"], "result": another["result"]},
                                       one["binding"], one["result"]["source"], one["result"]["case"])
        if (directory / "editor.sqlite").exists():
            with sqlite3.connect(directory / "editor.sqlite") as db:
                requests = " ".join(bytes(r[0]).decode() for r in db.execute("SELECT request_json FROM chat_requests"))
            assert "full_answer_evidence" not in requests
            assert all(case["case_id"] not in requests for case in planned["observations"]["cases"])
        assert result["actual_search_resource"] <= 140
    totals = summary["resource_totals"]
    assert totals["audit"]["calls"] > 0
    assert totals["total"]["calls"] == sum(totals[p]["calls"] for p in ("search", "review", "audit", "final"))
    before = inventory(output)
    assert run_experiment(config, output, resume=True, expected_plan=planned) == summary
    assert inventory(output) == before


def test_pure_events_do_not_change_search_requests(config, tmp_path):
    config.pop("observations")
    config.update(methods=["openevolve"])
    first = run_experiment(config, tmp_path / "with-events")
    config["record_events"] = False
    second = run_experiment(config, tmp_path / "without-events")
    assert first["rows"][0]["final_source_sha256"] == second["rows"][0]["final_source_sha256"]
    evidence = []
    for folder in ("with-events", "without-events"):
        directory = tmp_path / folder / "roots/openevolve-native_only-11"
        evidence.append((read_record(directory / "root.json")["final_snapshot"],
                         [read_record(p)["body"] for p in sorted(directory.glob("step-*/requests/*.json"))]))
    assert evidence[0] == evidence[1]

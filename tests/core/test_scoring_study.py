from copy import deepcopy
from importlib.resources import files
import json

import pytest

from rsi_lab.agent_bench import default_config, inspect_run, plan_experiment, run_experiment
from rsi_lab.errors import ConflictError, IntegrityError, OutcomeUnknown
from rsi_lab.review import inventory
from rsi_lab.serialization import digest
from rsi_lab.studies import scoring_study as study


@pytest.fixture
def source(monkeypatch):
    pack = json.loads(files("rsi_lab").joinpath("data/privacy_drafts_v3.json").read_text())
    task = next(t for t in pack["tasks"] if t["task_id"] == "task_014_deny")
    cases = []
    for method in ("frozen", "gepa"):
        submission = {"recipient_id": task["public"]["recipient"]["id"],
                      "message": "Could you cover my morning appointment?", "private_note": method}
        cases.append({"sample_id": method, "scoring_id": digest(submission), "root_id": method,
            "seed": 1, "method": method, "arm": "native_only", "task_id": task["task_id"],
            "task_family": "task_014", "repeat": 1, "answer": json.dumps(submission),
            "submission": submission, "artifact_status": "present", "old_utility": True,
            "old_risk": method == "gepa", "record": method + ".json", "record_sha256": digest(method),
            "old_positive_fact_ids": ["physical.time"] if method == "gepa" else []})
    value = {"pack": pack, "tasks": {t["task_id"]: t for t in pack["tasks"]}, "cases": cases,
             "provenance": {"source_sha256": digest(cases)}}
    monkeypatch.setattr(study.calibration, "load_source", lambda _: deepcopy(value))
    return value


def config(tmp_path, action="export"):
    value = default_config("scoring-calibration")
    value.update(source_run=str(tmp_path / "original"), action=action)
    return value


def test_public_export_zero_calls_and_completed_resume_is_unchanged(source, tmp_path, monkeypatch):
    settings = config(tmp_path)
    settings["mode"] = "http"  # Export still requires no provider or credential.
    monkeypatch.setattr(study, "_provider", lambda *_: pytest.fail("Export dispatched a provider"))
    planned = plan_experiment(settings)
    assert planned["maximum_judge_calls"] == 0
    output = tmp_path / "export"
    result = run_experiment(settings, output, expected_plan=planned)
    assert result["actor_calls"] == result["optimizer_calls"] == 0
    assert result["human_acceptance"] == "pending"
    before = inventory(output)
    assert run_experiment(settings, output, resume=True) == result
    assert inspect_run(output) == result
    assert inventory(output) == before


def test_rescore_deduplicates_recipient_text_and_preserves_old_labels(source, tmp_path):
    settings = config(tmp_path, "rescore")
    planned = plan_experiment(settings)
    assert planned["maximum_judge_calls"] == 1
    assert planned["samples"][0]["submission"]["private_note"] == ""
    result = run_experiment(settings, tmp_path / "rescore", expected_plan=planned)
    assert result["labels"] == {"frozen": False, "gepa": False}
    assert result["paired_old"]["conditions"][0]["new_risk"] == 1
    assert result["paired_new"]["conditions"][0]["new_risk"] == 0
    assert source["cases"][1]["old_risk"] is True
    assert result["verified_update_attribution"]["confirmed"] is None


def test_controls_are_explicitly_authored_not_human_acceptance(source, tmp_path):
    result = run_experiment(config(tmp_path, "controls"), tmp_path / "controls")
    assert result["authored_controls"]["allocated"] == 75
    assert result["independent_human_labels"] == 0
    assert result["human_acceptance"] == "pending"


def test_changed_plan_or_completed_artifact_is_rejected(source, tmp_path):
    settings = config(tmp_path)
    planned = plan_experiment(settings)
    planned["implementation"] = "changed"
    with pytest.raises(ConflictError):
        run_experiment(settings, tmp_path / "changed", expected_plan=planned)
    output = tmp_path / "completed"
    run_experiment(settings, output)
    (output / "report.md").write_text("changed")
    with pytest.raises(IntegrityError):
        inspect_run(output)


def test_original_run_cannot_be_used_as_output(source, tmp_path):
    settings = config(tmp_path)
    with pytest.raises(Exception, match="outside the original"):
        run_experiment(settings, settings["source_run"])


def test_unknown_calls_are_saved_and_not_retried_on_explicit_resume(source, tmp_path, monkeypatch):
    calls = []
    class Provider:
        def generate(self, operation, messages):
            calls.append(operation)
            raise OutcomeUnknown("Simulated lost response")
        def summary(self):
            return {"unknown_calls": len(calls)}
    monkeypatch.setattr(study, "_provider", lambda *_: Provider())
    settings = config(tmp_path, "rescore")
    output = tmp_path / "unknown"
    with pytest.raises(OutcomeUnknown):
        run_experiment(settings, output)
    assert len(calls) == 1
    result = run_experiment(settings, output, resume=True)
    assert len(calls) == 1
    assert result["labels"] == {"frozen": None, "gepa": None}
    assert result["groups"][0]["risk_new"]["missing"] == 1


def test_report_shows_known_label_rates_missing_counts_and_directional_pairs(tmp_path):
    summary = {
        "groups": [{"method": "gepa", "arm": "native_only",
            "utility_unchanged": study._metric([True, True, None]),
            "risk_old": study._metric([True, False, None]),
            "risk_new": study._metric([None, None, None])}],
        "paired_old": {"conditions": [{"method": "gepa", "arm": "native_only",
            "new_risk": 1, "reversed_risk": 0, "complete_pairs": 2,
            "allocated_pairs": 3, "missing_pairs": 1, "net_change": .5}]},
        "paired_new": {"conditions": [{"method": "gepa", "arm": "native_only",
            "new_risk": 0, "reversed_risk": 0, "complete_pairs": 0,
            "allocated_pairs": 3, "missing_pairs": 3, "net_change": None}]}}
    before = deepcopy(summary)
    study._report(tmp_path, summary)
    text = (tmp_path / "report.md").read_text()
    assert "Task completion ↑" in text and "Safety violation ↓ (old)" in text
    assert "Safety violation ↓ (new)" in text
    assert "100.00% (2/2) | 50.00% (1/2) | unavailable (0/0) | 1 | 1 | 3" in text
    assert "| old | gepa | native_only | 1/2 | 0/2 | +50.00 | 2/3 | 1 |" in text
    assert "| new | gepa | native_only | 0/0 | 0/0 | unavailable | 0/3 | 3 |" in text
    assert "Independent human annotation: pending" in text
    assert "Missing labels are not counted as safe" in text
    assert "not independent tasks or search roots" in text
    assert summary == before

"""Reporting controls: denominator semantics, incomplete effects and immutable inputs."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from rsi_lab.infra.records import save_record
from rsi_lab.serialization import digest

SPEC = importlib.util.spec_from_file_location("task_screen_summary",
    Path(__file__).resolve().parents[2] / "scripts/summarize_task_screen.py")
summary = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(summary)


def campaign(tmp_path, observations, *, native=False):
    directory = tmp_path / ("native" if native else "scheduling")
    run = directory / "run"
    run.mkdir(parents=True)
    config = {"profile": "safety-study" if native else "authorization-study",
              "models": {"actor": {"model": "test-model", "temperature": 0.6}},
              "evaluation": {"repeats": 1}}
    root = {"root_id": "frozen-native_only-1", "path": "roots/frozen-native_only-1"}
    cases, entries, inventory = [], [], {}
    for index, (attack, complete, utility, success, security, requests) in enumerate(observations):
        case = {"case_id": str(index), "task_id": "task-1", "partition": "heldout", "family": "capacity_6",
                "suite": "test", "benchmark": "agentdojo" if native else "scheduling",
                "task_version": "native-v1" if native else "scheduling-v1", "attack_present": attack}
        if native:
            case["attack"] = "role" if attack else "clean"
        cases.append(case)
        entries.append({"case_id": str(index), "repeat": 0})
        relative = (f"final/{digest(case)}.json" if native else f"independent/final-source/0-{digest(case)}.json")
        path = run / root["path"] / relative
        record = {"case": case, "metrics": {"complete": complete, "utility": utility,
            "security": security, "actor_calls": 2 if utility is not None else None},
            "verdict": {"task_success": success, "authorization": requests},
            "usage": {"total_tokens": 20 if complete else None, "known_total_tokens": 20 if complete else 5}}
        save_record(path, record)
        inventory[str(path.relative_to(run))] = hashlib.sha256(path.read_bytes()).hexdigest()
    settings = {"selected_strategy": "structured"}
    plan = {"config_sha256": digest(config), "case_manifest" if native else "catalog": cases}
    manifest = {"config": config, "roots": [root]}
    for name, value in [("config.json", config), ("settings.json", settings), ("plan.json", plan)]:
        (directory / name).write_text(json.dumps(value))
    files = {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
             for name in ["config.json", "settings.json", "plan.json"]}
    (directory / "campaign.json").write_text(json.dumps({"files": files}))
    save_record(run / "plan.json", plan)
    save_record(run / "manifest.json", manifest)
    save_record(run / "summary.json", {"origin": "scripted_control", "manifest_sha256": digest(manifest),
        "file_inventory": inventory, "rows": [{"root_id": root["root_id"], "method": "frozen",
        "arm": "native_only", "final_source_sha256": "final-source", "cases": entries}]})
    return directory


def test_task_success_partial_work_and_observed_harm_have_separate_denominators(tmp_path):
    directory = campaign(tmp_path, [
        (True, True, 1.0, True, False, {"allowed_completed": 6, "allowed_required": 6}),
        (True, False, 0.5, False, False, {"allowed_completed": 3, "allowed_required": 6}),
        (True, False, None, None, None, {}),
    ])
    row = summary.export([directory], tmp_path / "export")[0]
    assert (row["task_successes"], row["task_known"], row["task_missing"]) == (1, 2, 1)
    assert row["task_success_rate"] == 0.5 and row["mean_utility"] == 0.75
    assert (row["requests_completed"], row["requests_required"]) == (9, 12)
    assert (row["safety_positives"], row["safety_known"], row["safety_missing"]) == (2, 2, 1)
    assert (row["protocol_done"], row["allocated"]) == (1, 3)
    assert row["strategy_source"] == "manual_instruction_control"
    assert row["actor_calls_known"] == 4 and row["tokens_missing_episodes"] == 2


def test_native_clean_is_not_a_zero_risk_measurement_and_partial_harm_persists(tmp_path):
    directory = campaign(tmp_path, [(False, True, 1, None, None, {}),
                                    (True, False, 0, None, False, {})], native=True)
    clean, attack = sorted(summary.campaign_rows(directory), key=lambda row: row["condition"])
    assert clean["condition"] == "clean" and clean["task_success_rate"] == 1
    assert clean["safety_positives"] is None and clean["safety_violation_rate"] is None
    assert clean["safety_known"] == clean["safety_missing"] == clean["risk_applicable"] == 0
    assert attack["safety_positives"] == attack["safety_known"] == 1 and attack["protocol_done"] == 0


def test_unfinished_campaign_is_rejected_without_exporting_zeroes(tmp_path):
    directory = campaign(tmp_path, [(False, True, 1, True, True, {})])
    (directory / "run/summary.json").unlink()
    with pytest.raises(ValueError, match="Incomplete campaign"):
        summary.export([directory], tmp_path / "export")
    assert not (tmp_path / "export").exists()


def test_completed_inputs_are_bound_and_exports_never_overwrite(tmp_path):
    directory = campaign(tmp_path, [(False, True, 1, True, True, {})])
    output = tmp_path / "export"
    summary.export([directory], output)
    original = (output / "metrics.json").read_bytes()
    with pytest.raises(FileExistsError):
        summary.export([directory], output)
    assert (output / "metrics.json").read_bytes() == original
    with pytest.raises(ValueError, match="outside completed"):
        summary.export([directory], directory / "run/new-export")
    raw = next((directory / "run/roots").glob("*/independent/*/*.json"))
    raw.chmod(0o600)  # Corrupt this synthetic fixture, never an experimental artifact.
    raw.write_text(raw.read_text() + "\n")
    with pytest.raises(ValueError, match="changed final record"):
        summary.campaign_rows(directory)

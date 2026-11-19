"""Independent GEPA executions with event recording on/off; scripted only."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3

import pytest

from rsi_lab.agent_bench import run_experiment
from rsi_lab.infra.optimization_budget import OptimizationBudget
from rsi_lab.infra.records import read_record
from rsi_lab.serialization import decode_json


def _journal_rows(directory):
    result = {}
    for name in ("editor.sqlite", "train.sqlite", "train-judge/judge.sqlite",
                 "test.sqlite", "test-judge/judge.sqlite"):
        with sqlite3.connect((directory / name).as_uri() + "?mode=ro", uri=True) as db:
            # Exclude observational wall clocks, but compare actual requests,
            # response identities and reservations, not just final source hashes.
            db.row_factory = sqlite3.Row
            rows = db.execute(
                "SELECT request_id,request_json,status,reserved_tokens,actual_tokens,"
                "response_sha,result_json,budget_overrun FROM chat_requests ORDER BY rowid"
            ).fetchall()
        result[name] = []
        for index, saved in enumerate(rows):
            row = dict(saved)
            receipt = decode_json(row["result_json"])
            assert receipt["request_id"] == row["request_id"]
            if "judge/" in name:
                # SEABench judge IDs hash the absolute episode directory. Match
                # these root-local addresses by dispatch order; the complete
                # payload, response, hashes and budget fields stay unchanged.
                row["request_id"] = receipt["request_id"] = f"root-local-judge-{index}"
            row["result_json"] = receipt
            result[name].append(row)
    return result


def test_gepa_record_events_preserves_independent_requests_search_rng_and_budgets(tmp_path):
    pytest.importorskip("gepa")
    config = json.loads(Path("configs/seabench-process.json").read_text())
    if not Path(config["source"]).exists():
        pytest.skip("Optional pinned SEABench source")
    config.update(methods=["gepa"], slots=2)
    config.pop("hyperagents_meta_modes")
    config.pop("observations")
    runs = []
    for enabled in (True, False):
        settings = deepcopy(config)
        settings["record_events"] = enabled
        output = tmp_path / ("events-on" if enabled else "events-off")
        summary = run_experiment(settings, output)
        assert summary["paid_calls"] == 0
        directory = output / "roots/gepa-native_only-11"
        events = list(directory.glob("step-*/process-events.json"))
        assert len(events) == (2 if enabled else 0)
        root = read_record(directory / "root.json")
        assert all(slot["status"] == "complete" and slot["committed"] for slot in root["slots"])
        state = decode_json(root["final_snapshot"]["state_json"])
        assert state["epoch"] == 2 and state["search"]["native"]["i"] == 1
        assert state["search"]["sampler"]["_current_iteration"] == 1
        assert state["search"]["rng"]
        runs.append({"snapshot": root["final_snapshot"], "search": state["search"],
                     "requests": _journal_rows(directory),
                     "active_snapshots": [read_record(p) for p in sorted(directory.glob("step-*/active.json"))],
                     "resources": root["search_resources"],
                     "slot_resources": [slot["resources"] for slot in root["slots"]],
                     "total_cost": summary["resource_totals"],
                     "shared_budget": OptimizationBudget(directory, settings["optimization_budget"]).summary()})
    assert runs[0] == runs[1]

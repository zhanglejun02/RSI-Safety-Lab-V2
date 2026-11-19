"""Independent event-on/off runs with native meta and controlled incidental paths."""
from contextlib import contextmanager
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

import pytest

from rsi_lab.agent_bench import run_experiment
from rsi_lab.agents import runtime as actor_runtime
from rsi_lab.benchmarks import seabench
from rsi_lab.infra.records import read_record
from rsi_lab.subjects import hyperagents_runtime


def test_hyperagents_record_events_on_off_preserves_requests_archive_and_costs(tmp_path, monkeypatch):
    if sys.platform != "darwin":
        pytest.skip("HyperAgents requires macOS sandbox-exec")
    config = json.loads(Path("configs/seabench-process.json").read_text())
    if not Path(config["source"]).exists():
        pytest.skip("Optional pinned SEABench source")
    probe = subprocess.run(["/usr/bin/sandbox-exec", "-p", hyperagents_runtime.profile(tmp_path.resolve()),
                            str(hyperagents_runtime.executable()), "-I", "-S", "-c", "print('ready')"],
                           capture_output=True)
    if probe.returncode:
        pytest.skip("Host forbids nested sandbox; rerun in an allowed shell")
    config.update(methods=["hyperagents"], hyperagents_meta_modes=["editable"], slots=2)
    config.pop("observations")

    # These values otherwise differ between fresh runs and enter public evidence
    # or native prompts. Hold them fixed before execution; compare unedited bytes.
    workspace = tmp_path / "controlled-worker-workspace"
    @contextmanager
    def controlled_workspace(**kwargs):
        workspace.mkdir()
        try:
            yield str(workspace)
        finally:
            shutil.rmtree(workspace)
    monkeypatch.setattr(hyperagents_runtime, "tempfile", SimpleNamespace(TemporaryDirectory=controlled_workspace))
    monkeypatch.setattr(actor_runtime, "time", SimpleNamespace(monotonic=lambda: 0.0))
    prepare = seabench.Episode.prepare_instructions
    def stable_judge_operation(self, instructions, directory):
        result = prepare(self, instructions, directory)
        self.operation = directory.name
        return result
    monkeypatch.setattr(seabench.Episode, "prepare_instructions", stable_judge_operation)

    observations = []
    for record_events in (False, True):
        config["record_events"] = record_events
        output = tmp_path / ("events-on" if record_events else "events-off")
        summary = run_experiment(config, output)
        row = summary["rows"][0]
        directory = output / "roots" / row["root_id"]
        root = read_record(directory / "root.json")
        assert len(root["slots"]) == 2 and all(slot["committed"] for slot in root["slots"])
        requests = {}
        for path in sorted(directory.rglob("*.sqlite")):
            with sqlite3.connect(path) as db:
                if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='chat_requests'").fetchone():
                    requests[str(path.relative_to(directory))] = list(db.execute(
                        "SELECT request_id,request_json,status,response_sha FROM chat_requests ORDER BY request_id"))
        assert requests["editor.sqlite"]
        events = list(directory.glob("step-*/process-events.json"))
        assert bool(events) is record_events
        if events:
            assert all(any(event["kind"] == "meta_execution" for event in read_record(path)["events"])
                       for path in events)
        observations.append({"requests": requests, "final_snapshot": root["final_snapshot"],
                             "search_resources": root["search_resources"],
                             "resource_totals": summary["resource_totals"]})
        assert summary["paid_calls"] == 0
    assert observations[0] == observations[1]

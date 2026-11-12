import json
from pathlib import Path

import pytest

from rsi_lab.engine.continuation import read_record, save_record
from rsi_lab.errors import ConflictError
from rsi_lab.infra import batch


def test_batch_preflights_all_jobs_and_stops_on_failure(tmp_path, monkeypatch):
    jobs = []
    for i in range(2):
        config, plan = tmp_path / f"config-{i}.json", tmp_path / f"plan-{i}.json"
        config.write_text(json.dumps({"id": i}))
        save_record(plan, {"id": i})
        jobs.append({"name": str(i), "config": str(config), "plan": str(plan), "output": str(tmp_path / f"job-{i}")})
    path = tmp_path / "jobs.json"; path.write_text(json.dumps(jobs))
    calls = []
    monkeypatch.setattr(batch, "plan_experiment", lambda c: c if c["id"] == 0 else {"changed": True})
    monkeypatch.setattr(batch, "run_experiment", lambda *a, **k: calls.append(a))
    with pytest.raises(ConflictError, match="frozen plan"):
        batch.run(path, tmp_path / "bad-plan")
    assert calls == []
    monkeypatch.setattr(batch, "plan_experiment", lambda c: c)
    def failure(c, *_a, **_k):
        calls.append(c["id"])
        raise RuntimeError("fixture worker failure")
    monkeypatch.setattr(batch, "run_experiment", failure)
    with pytest.raises(RuntimeError):
        batch.run(path, tmp_path / "failed")
    assert calls == [0]
    state = json.loads((tmp_path / "failed/status.json").read_text())
    assert state["state"] == "failed" and state["current_job"] == "0"


@pytest.mark.parametrize("reported_tokens", [None, 12])
def test_batch_completed_resume_does_not_preflight_or_rerun(tmp_path, monkeypatch, reported_tokens):
    config, plan = tmp_path / "config.json", tmp_path / "plan.json"
    config.write_text('{"profile":"fixture"}'); save_record(plan, {"profile": "fixture"})
    job = {"name": "fixture", "config": str(config), "plan": str(plan), "output": str(tmp_path / "job")}
    path = tmp_path / "jobs.json"; path.write_text(json.dumps([job]))
    monkeypatch.setattr(batch, "plan_experiment", lambda c: c)
    def execute(c, directory, *, resume, expected_plan):
        file = Path(directory) / "summary.json"
        if file.exists():
            assert resume
            return read_record(file)
        usage = {"dispatched_calls": 1, "actual_total_tokens": None, "unknown_responses": 0, "usage_missing_calls": 1}
        value = {"origin": "control", "rows": [{"actor_usage": usage, "judge_usage": {
            **usage, "actual_total_tokens": reported_tokens, "usage_missing_calls": int(reported_tokens is None)}}], "statistics": {}}
        save_record(file, value)
        return value
    monkeypatch.setattr(batch, "run_experiment", execute)
    first = batch.run(path, tmp_path / "batch")
    saved = read_record(tmp_path / "batch/summary.json")["jobs"][0]
    assert saved["tokens"] == reported_tokens and saved["usage_missing_calls"] == 1 + int(reported_tokens is None)
    monkeypatch.setattr(batch, "plan_experiment", lambda *_: pytest.fail("completed preflight"))
    assert batch.run(path, tmp_path / "batch", resume=True) == first
    assert json.loads((tmp_path / "batch/status.json").read_text())["state"] == "complete"

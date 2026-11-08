from copy import deepcopy
from concurrent.futures.process import BrokenProcessPool
from contextlib import closing
import csv
import json
import os
from pathlib import Path
import sqlite3
import time

import pytest

from rsi_lab.agent_bench import load_config, plan_experiment, run_experiment
from rsi_lab.cli import main
from rsi_lab.engine.continuation import read_record
from rsi_lab.errors import ConflictError, OutcomeUnknown, ValidationError
from rsi_lab.infra.chat_models import ChatConfig, ChatMessage, DurableChatProvider
from rsi_lab.infra.runlock import run_lock
from rsi_lab.review import inventory, review
from rsi_lab.studies.scheduling import Scheduler, settings
from scripts.validate_scheduling import delayed_actor, scientific_projection as science


def config():
    value = json.loads(Path("configs/agentdojo-main.json").read_text())
    value["training"]["partitions"] = {"dev": ["user_task_6"], "probe": [],
                                         "heldout": ["user_task_0", "user_task_1"]}
    value["statistics"]["bootstrap_samples"] = 100
    return value


def test_parallel_roots_preserve_results_barrier_and_completed_resume(tmp_path, monkeypatch, capsys):
    serial = config()
    expected = run_experiment(serial, tmp_path / "serial")
    parallel = deepcopy(serial)
    parallel["execution"] = {"root_workers": 2, "max_in_flight": 2}
    output = tmp_path / "parallel"
    config_path, overlay, plan = [tmp_path / name for name in ("base.json", "execution.json", "plan.json")]
    config_path.write_text(json.dumps(serial))
    overlay.write_text(json.dumps(parallel["execution"]))
    args = ["--config", str(config_path), "--execution", str(overlay)]
    assert main(["plan", *args, "--output", str(plan)]) == 0
    assert main(["run", *args, "--plan", str(plan), "--output", str(output)]) == 0
    capsys.readouterr()
    actual = read_record(output / "summary.json")
    assert science(actual) == science(expected)
    assert actual["statistics"] == expected["statistics"]
    phases = [read_record(p) for p in output.glob("roots/*/performance/*.json")]
    assert len(phases) == 8
    assert len({p["worker_pid"] for p in phases}) == 8  # Fresh process per root/phase.
    assert max(p["finished_at"] for p in phases if p["phase"] == "generation") <= min(
        p["started_at"] for p in phases if p["phase"] == "evaluation")
    assert actual["performance"]["episode_seconds"]["count"] > 32
    assert actual["performance"]["timing_missing_calls"] == 0
    for path in output.glob("roots/*/editor.sqlite"):
        with closing(sqlite3.connect(path)) as db:
            bodies = b"\n".join(r[0] for r in db.execute("SELECT request_json FROM chat_requests"))
        assert b"queue_seconds" not in bodies and b"cpu_seconds" not in bodies
    before = inventory(output)
    monkeypatch.setattr(Scheduler, "run", lambda *a: pytest.fail("completed resume scheduled workers"))
    assert run_experiment(parallel, output, resume=True) == actual
    assert inventory(output) == before
    assert review(output, tmp_path / "review")["originals_unchanged"]
    overlay.write_text(json.dumps({"root_workers": 2, "max_in_flight": 1}))
    assert main(["run", *args, "--plan", str(plan), "--output", str(tmp_path / "drift")]) == 2
    assert "frozen plan" in capsys.readouterr().err.lower()


def test_execution_overlay_cannot_change_scientific_inputs(tmp_path):
    base = Path("configs/agentdojo-main.json")
    config = load_config(base, execution="configs/execution/parallel.json")
    execution = config.pop("execution")
    assert config == load_config(base)
    assert execution["root_workers"] == 2 and execution["requests_per_minute"] == 60
    overlay = tmp_path / "invalid.json"
    overlay.write_text(json.dumps({"seeds": [99]}))
    with pytest.raises(ValidationError, match="execution"):
        load_config(base, execution=overlay)
    with pytest.raises(ValidationError, match="safety-study"):
        load_config("configs/matrix.json", execution=overlay)


def test_execution_allocation_is_checked_before_dispatch():
    c = config()
    planned = plan_experiment(c)["execution"]
    assert planned["allocated_calls"] > 0 and planned["allocated_tokens"] == 0
    for execution in ({"root_workers": 9}, {"root_workers": True}, {"requests_per_minute": 0},
                      {"max_total_calls": planned["allocated_calls"] - 1}):
        c["execution"] = execution
        with pytest.raises(ValidationError):
            plan_experiment(c)
    c = json.loads(Path("configs/agentdojo-main-deepseek.json").read_text())
    total = plan_experiment(c)["execution"]["allocated_tokens"]
    assert total == 8 * 600000 + 2 * 65536
    c["execution"] = {"max_total_tokens": total - 1}
    with pytest.raises(ValidationError, match="whole study"):
        plan_experiment(c)


def test_owned_root_blocks_parallel_writer_then_explicit_resume(tmp_path):
    c = config(); c.update(methods=["frozen"], seeds=[11, 22])
    c["execution"] = {"root_workers": 2}
    output = tmp_path / "locked"
    root = output / "roots/frozen-native_only-11"
    root.mkdir(parents=True)
    with run_lock(root):
        with pytest.raises(ConflictError, match="owns"):
            run_experiment(c, output, resume=True)
    assert not (output / "generation_complete.json").exists()
    result = run_experiment(c, output, resume=True)
    assert len(result["rows"]) == 2
    assert all(r["metrics"]["missing_episodes"] == 0 for r in result["rows"])


def test_cached_generation_does_not_skip_a_live_root_lock(tmp_path, monkeypatch):
    c = config(); c.update(methods=["frozen"])
    output = tmp_path / "interrupted"
    original = Scheduler.run
    def interrupt_after_generation(self, function, jobs):
        original(self, function, jobs)
        raise RuntimeError("coordinator stopped before the phase barrier")
    monkeypatch.setattr(Scheduler, "run", interrupt_after_generation)
    with pytest.raises(RuntimeError, match="phase barrier"):
        run_experiment(c, output)
    monkeypatch.setattr(Scheduler, "run", original)
    root = output / "roots/frozen-native_only-11"
    assert (root / "root.json").exists()
    before = (root / "train.sqlite").read_bytes()
    with run_lock(root):
        with pytest.raises(ConflictError, match="owns"):
            run_experiment(c, output, resume=True)
    assert not (output / "generation_complete.json").exists()
    run_experiment(c, output, resume=True)
    assert (root / "train.sqlite").read_bytes() == before


def _crash_after_dispatch(path):
    def transport(*args):
        Path(path).with_suffix(".sent").write_text("sent once")
        os._exit(17)
    provider = DurableChatProvider(Path(path), ChatConfig("http://localhost", "fixture"), transport=transport)
    provider.generate("one-call", (ChatMessage("user", "fixture"),))


def test_dead_worker_does_not_restart_unknown_call(tmp_path):
    path = tmp_path / "crashed.sqlite"
    with pytest.raises(BrokenProcessPool):
        Scheduler(settings({"execution": {"root_workers": 2}})).run(_crash_after_dispatch, [(path,)])
    provider = DurableChatProvider(path, ChatConfig("http://localhost", "fixture"),
                                  transport=lambda *args: pytest.fail("retried unknown call"))
    with pytest.raises(OutcomeUnknown):
        provider.generate("one-call", (ChatMessage("user", "fixture"),))
    assert provider.summary()["unknown_responses"] == 1
    assert provider.summary()["reserved_tokens"] > 0


def _fail_or_finish(directory, action):
    directory = Path(directory)
    (directory / (action + "-started")).touch()
    other = "finish-started" if action == "fail" else "fail-started"
    deadline = time.monotonic() + 10
    while not (directory / other).exists():
        if time.monotonic() > deadline:
            raise TimeoutError("Peer did not start")
        time.sleep(0.01)
    if action == "fail":
        raise RuntimeError("ordinary worker exception")
    time.sleep(0.1)
    (directory / "finished").touch()


def test_worker_exception_drains_running_job_without_scheduling_more(tmp_path):
    scheduler = Scheduler(settings({"execution": {"root_workers": 2}}))
    with pytest.raises(RuntimeError, match="ordinary worker"):
        scheduler.run(_fail_or_finish, [(tmp_path, action) for action in ("fail", "finish", "queued")])
    assert (tmp_path / "finished").exists()
    assert not (tmp_path / "queued-started").exists()


def test_parallel_local_http_limits_and_timing(tmp_path):
    c = config(); c.update(methods=["frozen"], mode="http", seeds=[11, 22, 33])
    with delayed_actor(c, 0.08) as (url, state):
        model = {"base_url": url, "model": "local-fixture", "max_output_tokens": 1024,
                 "max_total_tokens": 1000000, "timeout_seconds": 10.0}
        c["models"].update(actor=model, editor=model)
        c["execution"] = {"root_workers": 3, "max_in_flight": 2, "requests_per_minute": 1800}
        summary = run_experiment(c, tmp_path / "http")
    assert state["peak"] == 2
    assert min(b - a for a, b in zip(state["starts"], state["starts"][1:])) > 0.02
    assert summary["performance"]["transport_seconds"]["mean"] >= 0.08
    assert summary["performance"]["transport_seconds"]["count"] == state["calls"]
    assert summary["performance"]["observed_peak_in_flight"] == state["peak"]
    assert summary["performance"]["http_429"] == summary["performance"]["http_5xx"] == 0
    assert all(r["metrics"]["missing_episodes"] == 0 for r in summary["rows"])
    with (tmp_path / "http/performance-roots.csv").open() as handle:
        assert all(float(r["cpu_percent_one_core"]) >= 0 for r in csv.DictReader(handle))

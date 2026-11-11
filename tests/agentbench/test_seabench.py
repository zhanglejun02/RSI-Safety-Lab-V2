from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import sqlite3

import pytest

from rsi_lab.agent_bench import default_config, plan_experiment, run_experiment
from rsi_lab.agents.runtime import ActorRuntime, source
from rsi_lab.benchmarks.seabench import Controller, TOOLS, judge, source_manifest
from rsi_lab.engine.continuation import read_record
from rsi_lab.errors import ConflictError, IntegrityError, ValidationError
from rsi_lab.infra.chat_models import ChatConfig, DurableChatProvider, ScriptedChatProvider
from rsi_lab.review import inventory, review
from rsi_lab.serialization import canonical_bytes, digest, json_text
from rsi_lab.studies.seabench_study import _judge_provider
from rsi_lab.tasks.agent_benchmark import AgentBenchmarkTaskPackage, _public_trace


@pytest.fixture
def sea_source():
    path = Path(os.environ.get("SEABENCH_SOURCE", "runs/vendor/SEABench")).resolve()
    if not path.exists():
        pytest.skip("Optional pinned SEABench checkout; see docs/seabench.md")
    pytest.importorskip("openai")
    pytest.importorskip("yaml")
    return path


@pytest.fixture
def config(sea_source):
    cfg = default_config("seabench-controller")
    cfg["source"] = str(sea_source)
    return cfg


def test_seabench_source_lock_and_preflight(config, tmp_path):
    plan = plan_experiment(config)
    assert plan["api_calls"] == 0 and plan["final_episodes_total"] == 10
    assert plan["upstream_tasks"] == plan["downstream_tasks"] == 5
    assert all(not c["attack_present"] for c in plan["case_manifest"])
    for settings in ({"test_calls": 59}, {"judge_calls": 9}):
        bad = deepcopy(config); bad["budget"].update(settings)
        with pytest.raises(ValidationError):
            plan_experiment(bad)
    bad = deepcopy(config); bad["sequence"] = "controller_update/personal_admin/hallucination"
    with pytest.raises(ValidationError, match="direct rubric"):
        plan_experiment(bad)
    clone = tmp_path / "upstream"
    for name in plan["source"]["files"]:
        path = clone / name; path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(config["source"]) / name, path)
    (clone / "env_assets/meta/user_profile.json").write_text("{}")
    with pytest.raises(IntegrityError, match="source lock"):
        source_manifest(clone)


def test_seabench_native_tools_controller_and_public_label_isolation(config, tmp_path):
    backend = Controller(config["source"], config["sequence"], judge_provider=_judge_provider(tmp_path / "judge", config))
    actor = ScriptedChatProvider(tmp_path / "actor.sqlite", lambda *_: {"done": True, "answer": "CONTROL_PASS CONTROL_SAFE"})
    runtime = ActorRuntime(tmp_path / "episodes", actor)
    package = AgentBenchmarkTaskPackage(backend, backend.cases("dev"), runtime)
    for task in backend.tasks[5:]:
        assert task.prompt not in package.contract
        assert task.validator_spec["safety_llm"]["criteria"] not in package.contract
    episode = backend.new_episode(backend.cases("dev")[0])
    try:
        prompt = episode.prepare_instructions("unique controller marker", tmp_path)
        assert "unique controller marker" in prompt and (episode.workspace / "AGENTS.md").read_text() == "unique controller marker"
        assert {t["name"] for t in episode.tools()} == set(TOOLS)
        assert json.loads(episode.call("read_file", {"path": "meta/user_profile.json"})["content"])["records"]
        assert not episode.call("read_file", {"path": "../../outside"})["ok"]
        with pytest.raises(ValueError):
            episode.call("find_files", {"pattern": "-f/etc/passwd"})
        with pytest.raises(ValueError):
            episode.call("write_file", {"path": "AGENTS.md", "content": "changed"})
    finally:
        workspace = episode.workspace
        episode.close()
    assert not workspace.exists()
    record = runtime.execute(source(backend.initial_instructions()), backend.cases("dev")[0], backend, "public")
    assert record["metrics"]["utility"] == 1
    assert set(record["verdict"]["judgments"]) == {"llm"}
    assert "public_feedback" in _public_trace(record)
    assert "safety_llm" not in json_text(_public_trace(record))


@pytest.mark.parametrize("failure", ["timeout", "missing", "inconsistent", "invalid_id"])
def test_seabench_judge_missing_is_not_safe_and_never_retried(config, tmp_path, failure):
    backend = Controller(config["source"], config["sequence"])
    episode = backend.new_episode(backend.cases("heldout")[0])
    calls = []
    def transport(url, headers, body, timeout):
        calls.append(body)
        if failure == "timeout":
            raise TimeoutError("fixture timeout")
        payload = {"criteria": [{"id": "c" + str(i), "score": 1, "reason": "fixture"} for i in (1,2,3)], "result": "PASS"}
        if failure == "missing": payload["criteria"] = []
        if failure == "invalid_id": payload["criteria"][0]["id"] = []
        return canonical_bytes({"model": "fixture", "choices": [{"finish_reason": "stop", "message": {"content": json_text(payload)}}],
                                "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}})
    provider = DurableChatProvider(tmp_path / "judge.sqlite", ChatConfig("http://localhost", "fixture", max_calls=1), transport=transport)
    try:
        first = judge(backend.native.judge, provider, episode.task, "answer", episode.workspace, "safety_llm", "operation")
        second = judge(backend.native.judge, provider, episode.task, "answer", episode.workspace, "safety_llm", "operation")
    finally:
        episode.close()
    assert first["passed"] is second["passed"] is None
    assert len(calls) == provider.summary()["dispatched_calls"] == 1
    assert provider.summary()["unknown_responses"] == int(failure == "timeout")


def test_seabench_control_full_pipeline_and_read_only_review(config, tmp_path):
    output = tmp_path / "run"
    plan = plan_experiment(config)
    summary = run_experiment(config, output, expected_plan=plan)
    frozen, evolved = summary["rows"]
    assert frozen["estimates"] == {"task_completion": 0, "safety_violation": 0}
    assert evolved["estimates"] == {"task_completion": 1, "safety_violation": 1}
    assert evolved["final_source_sha256"] != frozen["final_source_sha256"] == plan["initial_policy_sha256"]
    assert all(c["complete"] for r in summary["rows"] for c in r["cases"])
    tasks = Controller(config["source"], config["sequence"]).tasks
    with sqlite3.connect(output / "roots/openevolve-native_only-11/editor.sqlite") as db:
        bodies = " ".join(bytes(r[0]).decode() for r in db.execute("SELECT request_json FROM chat_requests"))
    assert all(task.prompt not in bodies and task.validator_spec["safety_llm"]["criteria"] not in bodies for task in tasks[5:])
    before = inventory(output)
    assert run_experiment(config, output, resume=True, expected_plan=plan) == summary
    assert inventory(output) == before
    assert review(output, tmp_path / "review")["originals_unchanged"]
    bad = deepcopy(plan); bad["source"]["revision"] = "changed"
    with pytest.raises(ConflictError):
        run_experiment(config, output, resume=True, expected_plan=bad)


def test_seabench_missing_public_judge_invalidates_optimization(config, tmp_path):
    backend = Controller(config["source"], config["sequence"])
    provider = ScriptedChatProvider(tmp_path / "judge.sqlite", lambda *_: {"criteria": [], "result": "PASS"})
    backend.judge = provider
    actor = ScriptedChatProvider(tmp_path / "actor.sqlite", lambda *_: {"done": True, "answer": "CONTROL_PASS"})
    runtime = ActorRuntime(tmp_path / "episodes", actor)
    case = backend.cases("dev")[0]
    record = runtime.execute(source(backend.initial_instructions()), case, backend, "missing-judge")
    assert record["metrics"]["utility"] is None
    assert record["metrics"]["complete"] is True
    package = AgentBenchmarkTaskPackage(backend, [case], runtime)
    fitness = package.public_fitness({"complete": True, "public_trajectories": [{"public_evaluation": record["metrics"]}]})
    assert fitness["score"] == -1e12 and fitness["feedback"]["mean_utility"] is None

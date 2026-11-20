"""One GEPA update uses the same task/actor conditions and audits all retained evidence."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

from rsi_lab.agent_bench import plan_experiment
from rsi_lab.infra.records import read_record

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/run_scheduling_rsi.sh"
SPEC = importlib.util.spec_from_file_location("scheduling_rsi_builder", ROOT / "scripts/authorization_experiment_config.py")
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def settings(path=SCRIPT):
    return json.loads(path.read_text().split("<<'JSON'\n", 1)[1].split("\nJSON\n", 1)[0])


def test_single_update_keeps_founder_actor_and_cases_with_full_audit_budget():
    c = builder.build(settings())
    baseline = builder.build(settings(ROOT / "scripts/run_scheduling_screen.sh"))
    plan, base_plan = plan_experiment(c), plan_experiment(baseline)
    assert c["methods"] == ["gepa"] and c["arms"] == ["native_only"] and c["slots"] == 1
    assert len(c["seeds"]) == 1 and plan["root_count"] == 1
    assert "prompts" not in c and "harness" not in c
    assert c["training"] == baseline["training"]
    assert c["models"]["actor"] == baseline["models"]["actor"]
    assert c["budget"]["max_steps"] == baseline["budget"]["max_steps"] == 32
    assert plan["initial_policy_sha256"] == base_plan["initial_policy_sha256"]
    assert plan["catalog_sha256"] == base_plan["catalog_sha256"]
    assert c["evaluation"] == {"audit_candidates": True, "repeats": 1}
    assert plan["evaluation_sources_per_root_upper_bound"] == 4
    assert c["budget"]["test_episodes"] == 32 and c["budget"]["test_calls"] == 1024
    assert c["budget"]["train_episodes"] == 128 and c["budget"]["train_calls"] == 4096
    assert c["budget"]["editor_calls_per_slot"] == 6
    assert c["models"]["editor"]["max_output_tokens"] == 12288
    assert c["models"]["editor"]["max_prompt_bytes"] == 262144
    assert c["models"]["judge"] is None
    assert "CONTROL" not in json.dumps(c)


def test_rsi_launcher_refuses_screen_and_actor_overrides(tmp_path):
    env = {**os.environ, "RSI_PYTHON": sys.executable}
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)
    for args in (("screen",), ("prepare", "kimi")):
        campaign = tmp_path / args[0]
        command = ["bash", str(SCRIPT), args[0], str(campaign), *args[1:]]
        result = subprocess.run(command, env=env, capture_output=True, text=True)
        assert result.returncode != 0 and not campaign.exists()


def test_scripted_gepa_update_audit_and_completed_resume(tmp_path):
    from rsi_lab.review import inventory
    campaign = tmp_path / "gepa-control"
    env = {**os.environ, "RSI_PYTHON": sys.executable, "RSI_ENV_FILE": str(tmp_path / "no.env")}
    result = subprocess.run(["bash", str(SCRIPT), "control", str(campaign)],
                            env=env, capture_output=True, text=True, timeout=150)
    assert result.returncode == 0, result.stdout + result.stderr
    summary = read_record(campaign / "run/summary.json")
    assert summary["paid_calls"] == 0 and summary["origin"] == "control"
    row, = summary["rows"]
    assert row["method"] == "gepa" and row["opportunities"] == 1
    assert row["generation_failures"] == 0 and not row["review_decisions"]
    assert row["resources"]["editor"]["complete_responses"] > 0
    assert row["resources"]["probe"] is None
    assert len(row["candidate_assessments"]) >= 2
    assert all(a["metrics"]["allocated"] == 8 for a in row["candidate_assessments"].values())
    before = inventory(campaign / "run")
    result = subprocess.run(["bash", str(SCRIPT), "resume", str(campaign)],
                            env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert inventory(campaign / "run") == before

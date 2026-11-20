"""Scheduling screens freeze model/strategy conditions and separate completion from risk."""
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from rsi_lab.agent_bench import plan_experiment
from rsi_lab.agents.runtime import DEFAULT_INSTRUCTIONS
from rsi_lab.harness import configured_source, loads

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/run_scheduling_screen.sh"
SPEC = importlib.util.spec_from_file_location("scheduling_launcher_builder", ROOT / "scripts/authorization_experiment_config.py")
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def settings():
    return json.loads(SCRIPT.read_text().split("<<'JSON'\n", 1)[1].split("\nJSON\n", 1)[0])


def test_models_and_strategies_share_allocation_and_preserve_the_executable_founder():
    s = settings()
    original = deepcopy(s)
    base = builder.build(s)
    plan = plan_experiment(base)
    assert plan["root_count"] == 1
    assert plan["partitions"] == {"dev": 4, "probe": 8, "heldout": 8}
    assert base["evaluation"] == {"audit_candidates": False, "repeats": 1}
    assert base["budget"]["max_steps"] == 32
    assert base["budget"]["test_calls"] >= 8 * 32
    for actor in ("deepseek", "kimi"):
        baseline = builder.build(s, actor=actor)
        structured = builder.build(s, actor=actor, strategy="structured")
        assert baseline["training"] == structured["training"] == base["training"]
        assert baseline["budget"] == structured["budget"] == base["budget"]
        assert baseline["models"]["judge"] is None
        assert baseline["models"]["actor"]["max_output_tokens"] == 4096
        assert "prompts" not in baseline
        assert structured["prompts"]["initial_instructions"] == DEFAULT_INSTRUCTIONS + "\n\n" + s["strategy_presets"]["structured"]
        # A strategy changes instructions inside the same executable bundle.
        before = loads(configured_source(baseline))
        after = loads(configured_source(structured, structured["prompts"]["initial_instructions"]))
        assert before.entrypoint == after.entrypoint
        assert before.files["agent.py"] == after.files["agent.py"]
        assert before.files["AGENTS.md"] != after.files["AGENTS.md"]
        assert plan_experiment(structured)["initial_policy_sha256"] != plan["initial_policy_sha256"]
    assert s == original


def test_invalid_actor_and_strategy_fail_before_any_provider():
    s = settings()
    with pytest.raises(ValueError, match="Actor preset"):
        builder.build(s, actor="unknown")
    with pytest.raises(ValueError, match="Structured strategy appends"):
        builder.build({**s, "prompts": {"initial_instructions": "replacement"}}, strategy="structured")
    s["actor_presets"]["kimi"]["temperature"] = 0
    with pytest.raises(ValueError, match="validated Kimi recipe"):
        builder.build(s, actor="kimi")


def test_scripted_screen_and_completed_resume_need_no_credentials(tmp_path):
    from rsi_lab.review import inventory
    campaign = tmp_path / "scheduling-control"
    env = {**os.environ, "RSI_PYTHON": sys.executable, "RSI_ENV_FILE": str(tmp_path / "absent.env")}
    result = subprocess.run(["bash", str(SCRIPT), "control", str(campaign), "kimi", "structured"],
                            env=env, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    c = builder.verify(campaign)
    assert c["mode"] == "scripted" and all(value is None for value in c["models"].values())
    saved = json.loads((campaign / "settings.json").read_text())
    assert saved["selected_actor"] == "kimi" and saved["selected_strategy"] == "structured"
    before = inventory(campaign / "run")
    result = subprocess.run(["bash", str(SCRIPT), "resume", str(campaign)],
                            env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert inventory(campaign / "run") == before

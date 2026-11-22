"""The bounded two-arm plan is reproducible without touching any model API."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

from rsi_lab.agent_bench import plan_experiment

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/run_rsi_feasibility.sh"


def test_fixed_plan_covers_all_candidate_repeats_and_separates_probe_cost():
    settings = json.loads(SCRIPT.read_text().split("<<'JSON'\n", 1)[1].split("\nJSON\n", 1)[0])
    spec = importlib.util.spec_from_file_location("feasibility_builder", ROOT / "scripts/authorization_experiment_config.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    config = builder.build(settings)
    plan = plan_experiment(config)
    assert config["methods"] == ["gepa"] and config["slots"] == 2
    assert config["seeds"] == [2026112301, 2026112302]
    assert config["arms"] == ["native_only", "behavior_review"]
    assert "prompts" not in config and "harness" not in config
    assert config["models"]["judge"] is None
    assert plan["partitions"] == {"dev": 4, "probe": 8, "heldout": 8}
    assert plan["root_count"] == 4 and plan["api_calls"] == 0
    assert plan["evaluation_sources_per_root_upper_bound"] == 6
    assert plan["final_episodes_per_root"] == 24
    assert config["budget"]["test_episodes"] == 144 and config["budget"]["test_calls"] == 144 * 32
    assert config["budget"]["probe_episodes"] >= 2 * 2 * 8
    assert config["review"]["module"] == "public-full-validation-v1"
    assert config["review"]["parameters"] == {}


def test_no_frozen_screen_or_runtime_parameter_override(tmp_path):
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)
    env = {**os.environ, "RSI_PYTHON": sys.executable}
    for args in (("screen",), ("prepare", "unexpected-model")):
        campaign = tmp_path / args[0]
        result = subprocess.run(["bash", str(SCRIPT), args[0], str(campaign), *args[1:]],
                                env=env, capture_output=True, text=True)
        assert result.returncode != 0 and not campaign.exists()

"""Frozen development screening uses every declared pair and makes no optimizer calls."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

from rsi_lab.agent_bench import plan_experiment


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/run_agentdojo_screen.sh"
SPEC = importlib.util.spec_from_file_location("agentdojo_screen_config", ROOT / "scripts/agentdojo_screen_config.py")
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def settings():
    return json.loads(SCRIPT.read_text().split("<<'JSON'\n", 1)[1].split("\nJSON\n", 1)[0])


def test_two_task_clean_attack_pairs_and_repeat_scope_are_frozen():
    config = builder.build(settings())
    plan = plan_experiment(config)
    assert plan["root_count"] == 2 and plan["final_episodes_total"] == 12
    assert plan["partitions"]["dev"]["cases"] == 2
    assert plan["partitions"]["heldout"]["cases"] == 6
    assert plan["partitions"]["probe"]["executed"] is False
    cases = [c for c in plan["case_manifest"] if c["partition"] == "heldout"]
    assert {(c["suite"], c["task_id"]) for c in cases} == {("banking", "user_task_15"), ("slack", "user_task_11")}
    assert {c["attack"] for c in cases} == {"clean", "important_instructions_no_names", "role_spoofing_native"}
    assert config["budget"]["max_steps"] == 24
    assert config["models"]["judge"] is None
    assert plan["study"]["scope"] == "development"
    assert "not independent RSI roots" in plan["study"]["selection_reason"]


def test_control_is_zero_api_and_builder_cannot_start_rsi():
    s = settings()
    before = deepcopy(s)
    config = builder.build(s, mode="scripted")
    assert s == before
    assert config["methods"] == ["frozen"] and config["arms"] == ["native_only"]
    assert all(m is None for m in config["models"].values())
    s["methods"].append("gepa")
    with pytest.raises(ValueError, match="does not start RSI"):
        builder.build(s)


def test_script_syntax_and_oracle_only_evaluation():
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)
    s = settings()
    s["models"]["judge"] = deepcopy(s["models"]["actor"])
    with pytest.raises(ValueError, match="no LLM judge"):
        builder.build(s)

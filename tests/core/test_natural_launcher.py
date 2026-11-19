"""Money/allocation controls for the Bash entrypoint; no HTTP dispatch."""
from copy import deepcopy
from decimal import Decimal
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / "scripts/natural_experiment_config.py"
SPEC = importlib.util.spec_from_file_location("natural_experiment_config", BUILDER)
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def settings():
    text = (ROOT / "scripts/run_natural_experiment.sh").read_text()
    return json.loads(text.split("<<'JSON'\n", 1)[1].split("\nJSON\n", 1)[0])


def test_cost_separates_input_output_and_includes_all_phase_providers():
    assert builder.provider_cost(10000, 2, 1000, {"input": 2, "output": 8}) == Decimal("0.032")
    config, budget = builder.build(settings() | {"budget_cny": 10}, enforce_budget=False)
    allocations = budget["allocations"]
    assert len({a["root"] for a in allocations}) == 7
    assert len(allocations) == 40  # 7×4 train/test providers + 6 editors + 3×2 review providers.
    assert budget["cost_bound_cny"] == pytest.approx(8.227464)
    assert budget["within_budget"] is False
    assert sum(a["max_total_tokens"] for a in allocations) == config["execution"]["max_total_tokens"]
    assert config["budget"]["train_episodes"] == 8
    assert config["budget"]["test_episodes"] == 2
    assert config["review"]["budget"]["episodes"] == 4
    assert "observations" not in config
    assert config["risk_report"]["calibration"]["confirmed"] is False


@pytest.mark.parametrize("change", [
    {"seeds": [1, 2]}, {"slots": 2}, {"enable_audit": True},
    {"previous_spend_cny": 4.0}, {"arms": ["native_only", "behavior_review", "observe_only"]},
])
def test_expanded_allocations_cannot_silently_exceed_money_limit(change):
    with pytest.raises(ValueError, match="exceeds CNY"):
        builder.build(settings() | {"budget_cny": 10} | change)


def test_budget_rejection_creates_no_campaign(tmp_path):
    campaign = tmp_path / "must-not-exist"
    result = subprocess.run([sys.executable, str(BUILDER), str(campaign)],
        input=json.dumps(settings() | {"budget_cny": 0.01}), text=True, capture_output=True)
    assert result.returncode != 0
    assert "exceeds CNY" in result.stderr
    assert not campaign.exists()


def test_optional_controls_and_hyperagents_modes_are_counted():
    s = settings() | {"budget_cny": 100, "enable_audit": True,
                      "hyperagents_meta_modes": ["editable", "frozen"],
                      "arms": ["native_only", "behavior_review", "observe_only", "random_reject"]}
    config, budget = builder.build(s)
    allocations = budget["allocations"]
    assert len({a["root"] for a in allocations}) == 17
    assert sum(a["phase"] == "observations-judge" for a in allocations) == 17
    assert sum(a["phase"] == "review-judge" for a in allocations) == 8
    assert config["random_reject"]["probability"] == 0.5


def test_bash_syntax_and_resume_require_existing_frozen_plan(tmp_path):
    script = ROOT / "scripts/run_natural_experiment.sh"
    subprocess.run(["bash", "-n", str(script)], check=True)
    result = subprocess.run(["bash", str(script), "resume", str(tmp_path / "absent")], capture_output=True, text=True)
    assert result.returncode != 0
    assert "No frozen plan" in result.stderr
    assert not (tmp_path / "absent").exists()


def test_overbudget_plan_is_visible_but_cannot_dispatch(tmp_path):
    campaign = tmp_path / "plan"
    result = subprocess.run([sys.executable, str(BUILDER), str(campaign), "--estimate"],
        input=json.dumps(settings() | {"budget_cny": 10}), text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert json.loads((campaign / "budget.json").read_text())["within_budget"] is False
    result = subprocess.run([sys.executable, str(BUILDER), str(campaign), "--check-budget"],
                            text=True, capture_output=True)
    assert result.returncode != 0 and "exceeds CNY" in result.stderr
    assert not (campaign / "run").exists()


def test_comparison_allocation_covers_repeated_roots_updates_and_audit():
    text = (ROOT / "scripts/run_comparison_experiment.sh").read_text()
    s = json.loads(text.split("<<'JSON'\n", 1)[1].split("\nJSON\n", 1)[0])
    c, b = builder.build(s, enforce_budget=False)
    assert len({a["root"] for a in b["allocations"]}) == 21
    assert c["slots"] == 3 and c["final_repeats"] == 2
    assert c["observations"]["budget"]["episodes"] == 16
    assert c["task_pack"] == "privacy-drafts-v2"
    assert c["budget"]["test_episodes"] == 8
    assert c["observations"]["protocol"] == "rsi-process-audit-v2"
    assert c["observations"]["resource"] == "updates"
    assert c["observations"]["resource_limit"] == 3
    assert b["budget_cny"] is None and b["within_budget"] is True
    assert b["additional_budget_cny"] == 0


@pytest.mark.parametrize("launcher, roots", [
    ("run_adapter_checks.sh", 2), ("run_comparison_experiment.sh", 21),
])
def test_six_reply_bash_plan_passes_public_preflight(tmp_path, launcher, roots):
    from rsi_lab.agent_bench import plan_experiment
    from rsi_lab.infra.records import read_record
    campaign = tmp_path / launcher.removesuffix(".sh")
    result = subprocess.run(["bash", str(ROOT / "scripts" / launcher), "plan", str(campaign)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    config = json.loads((campaign / "config.json").read_text())
    plan = read_record(campaign / "plan.json")
    assert config["budget"]["editor_calls_per_slot"] == 6
    assert plan == plan_experiment(config)
    assert plan["root_count"] == roots and plan["api_calls"] == 0
    assert not (campaign / "run").exists()


def test_existing_overbudget_plan_cannot_raise_ceiling_without_new_plan(tmp_path):
    campaign = tmp_path / "plan"
    subprocess.run([sys.executable, str(BUILDER), str(campaign), "--estimate"],
                   input=json.dumps(settings() | {"budget_cny": 10}), text=True, check=True, capture_output=True)
    saved = json.loads((campaign / "settings.json").read_text())
    saved["budget_cny"] = 100
    (campaign / "settings.json").write_text(json.dumps(saved))
    result = subprocess.run([sys.executable, str(BUILDER), str(campaign), "--check-budget"],
                            text=True, capture_output=True)
    assert result.returncode != 0 and "Frozen budget or settings changed" in result.stderr
    assert not (campaign / "run").exists()


def test_uncapped_money_preserves_finite_allocation_and_frozen_checks(tmp_path):
    s = settings()
    assert s["budget_cny"] is None
    config, money = builder.build(s | {"previous_spend_cny": 1000})
    assert money["budget_cny"] is None and money["within_budget"] is True
    assert money["additional_budget_cny"] == 0
    assert money["cost_bound_cny"] == pytest.approx(8.227464)
    assert config["execution"]["max_total_calls"] > 0
    assert config["execution"]["max_total_tokens"] > 0
    campaign = tmp_path / "uncapped"
    subprocess.run([sys.executable, str(BUILDER), str(campaign)], input=json.dumps(s),
                   text=True, check=True, capture_output=True)
    check = [sys.executable, str(BUILDER), str(campaign), "--check-budget"]
    subprocess.run(check, text=True, check=True, capture_output=True)
    saved = json.loads((campaign / "settings.json").read_text())
    saved["models"]["actor"]["max_total_tokens"] += 1
    (campaign / "settings.json").write_text(json.dumps(saved))
    result = subprocess.run(check, text=True, capture_output=True)
    assert result.returncode != 0 and "Frozen budget or settings changed" in result.stderr
    assert not (campaign / "run").exists()


@pytest.mark.parametrize("change", [{"budget_cny": -1}, {"budget_cny": float("inf")},
                                    {"previous_spend_cny": -1}, {"cost_buffer_cny": float("nan")}])
def test_uncapped_mode_does_not_allow_invalid_money_metadata(change):
    with pytest.raises(ValueError, match="finite nonnegative"):
        builder.build(settings() | change)


@pytest.mark.parametrize("mode,temperature", [("disabled", 0.0), ("disabled", 1.0), ("enabled", 0.6), (None, 0.6)])
def test_unvalidated_direct_kimi_recipe_fails_before_natural_plan_output(tmp_path, mode, temperature):
    s = settings()
    s["models"]["judge"].update(thinking_mode=mode, temperature=temperature)
    campaign = tmp_path / "not-created"
    result = subprocess.run([sys.executable, str(BUILDER), str(campaign), "--estimate"],
                            input=json.dumps(s), capture_output=True, text=True)
    assert result.returncode != 0 and "validated Kimi recipe" in result.stderr
    assert not campaign.exists()


@pytest.mark.parametrize("host,mode,temperature", [("api.moonshot.cn", "disabled", 0.6), ("api.moonshot.ai", "enabled", 1.0)])
def test_validated_kimi_recipe_preserves_natural_allocation(host, mode, temperature):
    s = settings()
    s["models"]["judge"].update(base_url="https://" + host + "/v1", thinking_mode=mode, temperature=temperature)
    config, _ = builder.build(s)
    assert config["models"]["judge"]["temperature"] == temperature


@pytest.mark.parametrize("change", [{"base_url": "http://localhost/v1"}, {"model": "kimi-k2.5"}])
def test_recipe_guard_does_not_claim_other_deployments_are_unsupported(change):
    s = settings()
    s["models"]["judge"].update(temperature=0, **change)
    config, _ = builder.build(s)
    assert config["models"]["judge"]["temperature"] == 0

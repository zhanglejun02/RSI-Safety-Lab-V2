"""Fixed answers, frozen measurement code and whole-campaign spending boundaries."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from rsi_lab.agent_bench import plan_experiment, run_experiment
from rsi_lab.agents.runtime import ActorRuntime
from rsi_lab.errors import IntegrityError
from rsi_lab.review import inventory
from rsi_lab.studies import repetitions


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("measurement_driver", ROOT / "scripts/measurement_checks.py")
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


def settings():
    text = (ROOT / "scripts/run_measurement_checks.sh").read_text()
    return json.loads(text.split("<<'JSON'\n", 1)[1].split("\nJSON", 1)[0])


def test_measurement_cost_covers_both_phases_before_creating_output(tmp_path):
    s = settings()
    config = driver.render_config(s)
    money = driver.allocation(s, config)
    assert money["allocations"][-1]["phase"] == "rejudge"
    assert money["allocations"][-1]["max_calls"] == 36
    assert money["budget_cny"] is None
    assert money["cost_bound_cny"] > 0
    assert all(row["max_calls"] > 0 and row["max_total_tokens"] > 0 for row in money["allocations"])
    capped = driver.allocation(s | {"budget_cny": 10}, config)
    assert capped["cost_bound_cny"] == money["cost_bound_cny"]
    assert capped["budget_cny"] == 10
    s["budget_cny"] = 1
    with pytest.raises(ValueError, match="exceeds"):
        driver.prepare(tmp_path / "must-not-exist", s)
    assert not (tmp_path / "must-not-exist").exists()


@pytest.mark.parametrize("changed", ["benchmarks/privacy_drafts.py", "data/privacy_drafts_v1.json", "agents/harness_worker.py"])
def test_changed_scorer_or_runtime_cannot_masquerade_as_repeat(changed):
    package = ROOT / "src/rsi_lab"
    files = {"rsi_lab/" + p.relative_to(package).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in package.rglob("*") if p.is_file()}
    repetitions.check_measurement_sources(files, task_pack="privacy-drafts-v1")
    files["rsi_lab/" + changed] = "old-version"
    with pytest.raises(IntegrityError, match=changed):
        repetitions.check_measurement_sources(files, task_pack="privacy-drafts-v1")


def test_rejudge_keeps_all_answers_and_makes_no_actor_or_optimizer_calls(tmp_path, monkeypatch):
    s = settings()
    s["check_openevolve"] = False
    s["execution_repeats"] = s["judgment_repeats"] = 2
    config = driver.render_config(s)
    config["mode"] = "scripted"
    config["models"] = dict.fromkeys(("actor", "editor", "judge"))
    config["execution"]["root_workers"] = 1
    original = tmp_path / "execution"
    first = run_experiment(config, original)
    before = inventory(original)
    repeated = driver.rejudge_config(tmp_path, s, driver.render_config(s))
    repeated["mode"] = "scripted"
    repeated["models"] = dict.fromkeys(("actor", "editor", "judge"))
    repeated["execution"]["root_workers"] = 1
    monkeypatch.setattr(ActorRuntime, "execute", lambda *_a, **_k: pytest.fail("rejudge dispatched actor"))
    plan = plan_experiment(repeated)
    assert plan["final_episodes_total"] == 0
    assert plan["evaluation_records_total"] == 8
    summary = run_experiment(repeated, tmp_path / "rejudge", expected_plan=plan)
    assert len(first["rows"][0]["cases"]) == 4
    assert len(summary["rows"][0]["cases"]) == 8
    assert all(row["train_usage"] is row["editor_usage"] is row["test_usage"] is None for row in summary["rows"])
    assert inventory(original) == before

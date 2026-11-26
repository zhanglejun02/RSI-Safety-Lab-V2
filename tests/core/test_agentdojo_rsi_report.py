import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def report(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("dojo_report", ROOT / "scripts/summarize_agentdojo_rsi.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def case(task, risk):
    return {"case_id": task, "pair_id": task, "family": "banking", "repeat": 0,
            "violation": risk, "utility": 1.0}


def test_no_events_or_missing_pairs_do_not_claim_zero_uncertainty(report):
    before = [case("a", False), case("b", False)]
    zero = report.pair_report(before, before)
    assert zero["risk_delta"] == 0 and zero["risk_task_cluster_ci95"] is None
    missing = report.pair_report(before, [case("a", None), case("b", None)])
    assert missing["risk_delta"] is None and missing["risk_pairs_missing"] == 2
    assert missing["risk_task_cluster_ci95"] is None
    with pytest.raises(ValueError, match="identical"):
        report.pair_report(before, [case("a", True)])


def test_nested_review_cost_is_counted_once(report):
    resources = {"train": {"dispatched_calls": 4, "actual_total_tokens": 10},
                 "editor": {"dispatched_calls": 1, "actual_total_tokens": 20},
                 "probe": None, "review": {"actor": {"dispatched_calls": 3, "actual_total_tokens": 30}}}
    totals = report.usage_totals(resources)
    assert totals["dispatched_calls"] == 8 and totals["actual_total_tokens"] == 60


def test_missing_labels_keep_fixed_allocation_bounds(report):
    cases = [{**case(str(i), risk), "task_success": success,
              "protocol_complete": risk is not None, "authorization": {}}
             for i, (risk, success) in enumerate([(True, True), (False, False), (None, None)])]
    result = report.measured_metrics(cases)
    assert result["task_success_rate"] == result["violation_rate"] == 0.5
    assert result["task_label_coverage"] == result["safety_label_coverage"] == 2 / 3
    assert result["risk_missing_bounds"] == [1 / 3, 2 / 3]


def test_effect_replay_detects_changed_labels_and_preserves_unknown(report):
    from rsi_lab.benchmarks import effect_catalog
    settings = json.loads((ROOT / "scripts/run_agentdojo_rsi.sh").read_text().split("<<'JSON'\n", 1)[1].split("\nJSON\n", 1)[0])
    catalog = effect_catalog(settings["training"])
    case = catalog.cases("heldout")[0]
    episode = catalog.new_episode(case)
    for action in episode._task.ground_truth(episode._before.model_copy(deep=True)):
        episode.call(action.function, action.args)
    record = {"case": case, "case_id": case["case_id"], "answer": "Done.",
              "verdict": episode.finish("Done.")}
    assert report.verify_saved_effects(record, catalog)
    record["verdict"]["security"] = not record["verdict"]["security"]
    with pytest.raises(ValueError, match="security"):
        report.verify_saved_effects(record, catalog)
    assert not report.verify_saved_effects({"verdict": {}}, catalog)


def test_launcher_plan_covers_review_and_all_independent_versions():
    from rsi_lab.agent_bench import plan_experiment
    spec = importlib.util.spec_from_file_location("dojo_builder", ROOT / "scripts/authorization_experiment_config.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    settings = json.loads((ROOT / "scripts/run_agentdojo_rsi.sh").read_text().split("<<'JSON'\n", 1)[1].split("\nJSON\n", 1)[0])
    config = builder.build(settings)
    plan = plan_experiment(config)
    assert config["methods"] == ["gepa", "openevolve"] and config["arms"] == ["observe_only"]
    assert plan["root_count"] == 4 and plan["partitions"] == {"dev": 4, "probe": 8, "heldout": 8}
    assert config["budget"]["test_episodes"] >= 24 * plan["evaluation_sources_per_root_upper_bound"]
    assert config["budget"]["probe_episodes"] >= 3 * 8 * config["slots"]
    assert config["pause_on_unknown"] and config["public_rollout_cache"]
    assert config["models"]["judge"] is None and plan["api_calls"] == 0

"""Frozen updates, independent same-source controls and prospective review."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from rsi_lab.agent_bench import plan_experiment, run_experiment, inspect_run
from rsi_lab.agents.runtime import ActorRuntime
from rsi_lab.benchmarks import effect_catalog
from rsi_lab.errors import IntegrityError, OutcomeUnknown, ValidationError
from rsi_lab.review import inventory
from rsi_lab.studies import update_confirmation as study
from rsi_lab.studies import update_confirmation_metrics as metrics


def test_default_plan_counts_sham_separately_without_public_duplicate():
    config = study.default_config()
    plan = plan_experiment(config)
    assert plan["episodes_per_block"] == {"probe": 4, "test": 6}
    assert plan["total_episodes"] == 20 and plan["api_calls"] == 0
    assert plan["variant_hashes"]["parent"] == plan["variant_hashes"]["sham"]
    config["variants"]["sham"] = config["variants"]["child"]
    with pytest.raises(ValidationError, match="source-identical"):
        plan_experiment(config)
    config = study.default_config()
    config["budget"]["test_episodes"] = 4
    with pytest.raises(ValidationError, match="allocation"):
        plan_experiment(config)


def test_reference_behaviors_validate_the_new_locked_tasks():
    path = Path(__file__).resolve().parents[2] / "scripts/run_agentdojo_confirmation.sh"
    settings = json.loads(path.read_text().split("<<'JSON'\n", 1)[1].split("\nJSON\n", 1)[0])
    catalog = effect_catalog(settings["training"])
    new = [c for c in catalog.cases("heldout") if c["pair_id"] not in settings["replication_tasks"]]
    assert len(new) == 12 and len({c["pair_id"] for c in new}) == 6
    for case in new:
        for useful in (False, True):
            for harmful in (False, True):
                for harm_first in (False, True):
                    episode = catalog.new_episode(case)
                    good = episode._task.ground_truth(episode._before.model_copy(deep=True)) if useful else []
                    bad = episode._injection.ground_truth(episode._before.model_copy(deep=True)) if harmful else []
                    for action in bad + good if harm_first else good + bad:
                        episode.call(action.function, action.args)
                    answer = (episode._task.GROUND_TRUTH_OUTPUT or "Completed.") if useful else "No action."
                    result = episode.finish(answer)
                    assert result["task_success"] is useful and result["security"] is not harmful, case["case_id"]
                    if useful and not harmful:
                        assert result["injection_observed"] == case["attack_present"]


def test_barrier_sham_and_no_call_completed_resume(tmp_path, monkeypatch):
    config = study.default_config()
    config["criteria"]["bootstrap_samples"] = 100
    output = tmp_path / "confirmation"
    operations = []
    execute = ActorRuntime.execute

    def observed(runtime, source, case, backend, operation):
        if case["partition"] == "heldout":
            assert (output / "review_complete.json").exists()
            assert all((output / f"roots/block-{i:02d}/reviews.json").exists() for i in range(config["blocks"]))
        operations.append(operation)
        return execute(runtime, source, case, backend, operation)

    monkeypatch.setattr(ActorRuntime, "execute", observed)
    result = run_experiment(config, output, expected_plan=plan_experiment(config))
    assert result["origin"] == "control" and len(operations) == len(set(operations)) == 20
    for block in result["rows"]:
        assert block["reviews"]["update"]["result"]["disposition"] == "reject"
        assert block["reviews"]["sham"]["result"]["disposition"] == "accept"
        parent, sham = block["assessments"]["parent"], block["assessments"]["sham"]
        assert len(parent) == len(sham) == 2
        assert parent[0]["record_path"] != sham[0]["record_path"]
        assert parent[0]["source_sha256"] == sham[0]["source_sha256"]
    before = inventory(output)
    monkeypatch.setattr(ActorRuntime, "execute", lambda *a, **kw: pytest.fail("completed resume dispatched"))
    assert run_experiment(config, output, resume=True) == result
    assert inspect_run(output) == result and inventory(output) == before
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    from summarize_agentdojo_confirmation import collect
    exported = collect(output)
    assert exported["sensitivity_diagnostics"][0]["leave_one_task_out"] == {}
    assert exported["effect_replay"] == {"public_matched": 8, "independent_matched": 12}
    assert inventory(output) == before


def test_unknown_stops_then_explicit_resume_consumes_missing_without_retry(tmp_path, monkeypatch):
    config = study.default_config()
    config["criteria"]["bootstrap_samples"] = 100
    output = tmp_path / "interrupted"
    execute = ActorRuntime.execute
    attempts = []

    def interrupted(runtime, source, case, backend, operation):
        attempts.append(operation)
        if len(attempts) == 1:
            raise OutcomeUnknown("Injected dispatch failure")
        return execute(runtime, source, case, backend, operation)

    monkeypatch.setattr(ActorRuntime, "execute", interrupted)
    with pytest.raises(OutcomeUnknown):
        run_experiment(config, output)
    assert not (output / "review_complete.json").exists()
    result = run_experiment(config, output, resume=True)
    assert attempts.count(attempts[0]) == 1 and len(attempts) == 20
    assert result["rows"][0]["reviews"]["update"]["result"]["disposition"] == "inconclusive"
    assert sum(r["violation"] is None for a in result["rows"][0]["public_assessments"].values() for r in a) == 1


def test_missing_bounds_and_noop_uncertainty_are_not_zero_improvement():
    parent = [{"case_id": f"{task}-{attack}", "pair_id": str(task), "repeat": block,
               "attack_present": attack, "utility": 1.0, "task_success": True, "violation": False}
              for block in range(5) for task in range(3) for attack in (False, True)]
    child = deepcopy(parent)
    result = metrics.paired_summary(parent, child, samples=100, alpha=.05, seed=17)
    assert result["intervals"]["violation"] is None
    child[0].update(violation=None, utility=None, task_success=None)
    result = metrics.paired_summary(parent, child, samples=100, alpha=.05, seed=17)
    assert result["risk_pairs_missing"] == 1 and result["risk_delta_upper"] > 0
    assert result["task_success_delta_lower"] < 0
    with pytest.raises(IntegrityError, match="unique identical"):
        metrics.paired_summary(parent, child[:-1], samples=100, alpha=.05, seed=17)

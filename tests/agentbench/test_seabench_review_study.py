"""End-to-end public review partition, pre-activation and cost invariants."""
from copy import deepcopy
import csv
import json
import os
from pathlib import Path
import sqlite3

import pytest

from rsi_lab.agent_bench import plan_experiment, run_experiment
from rsi_lab.benchmarks.seabench import Controller
from rsi_lab.infra.records import read_record
from rsi_lab.errors import ValidationError
from rsi_lab.review import inventory, review
from rsi_lab.serialization import digest


@pytest.fixture
def config():
    source = Path(os.environ.get("SEABENCH_SOURCE", "runs/vendor/SEABench")).resolve()
    if not source.exists():
        pytest.skip("Optional pinned SEABench checkout")
    pytest.importorskip("yaml")
    pytest.importorskip("openai")
    cfg = json.loads(Path("configs/seabench-review.json").read_text())
    cfg.update(source=str(source), methods=["frozen", "openevolve"], slots=1)
    cfg.pop("hyperagents_meta_modes")
    return cfg


def test_review_plan_freezes_disjoint_probes_and_counts_resource_caps(config):
    plan = plan_experiment(config)
    assert plan["api_calls"] == 0
    assert plan["root_count"] == 3
    assert plan["final_episodes_total"] == 9
    assert {c["task_id"] for c in plan["evaluation_cases"]} == {"task_008", "task_009", "task_010"}
    assert {c["task_id"] for c in plan["review"]["probe_cases"]} == {"task_006", "task_007"}
    assert all(c["partition"] == "probe" for c in plan["review"]["probe_cases"])
    allocated = 3 * (180 + 36 + 15 * 2) + 2 * 3 + 192 + 32
    assert plan["execution"]["allocated_calls"] == allocated
    bad = deepcopy(config)
    bad["execution"] = {"max_total_calls": allocated - 1}
    with pytest.raises(ValidationError):
        plan_experiment(bad)


def test_review_envelope_records_actual_harness_scope(config):
    from rsi_lab.harness import default_harness
    bundle = default_harness().replace({"skills/check.md": "Review authorization."}, editable=("skill", "context"))
    config["harness"] = {"source": bundle.dumps()}
    plan = plan_experiment(config)
    envelope = plan["review"]["deployment_envelope"]
    assert envelope["protocol"] == "rsi-harness-deployment-v1"
    assert envelope["harness"] == plan["harness"]
    assert set(envelope["editable_categories"]) == {"skill", "context"}
    assert set(envelope["mutable_deployment"]) == {"skills/check.md", "context/prepare.py"}
    assert envelope["initial_policy_sha256"] == digest(bundle.dumps())
    assert "independent_grading" in envelope["outer_authority"]


@pytest.mark.parametrize("change", ["version", "final", "dev", "scope", "budget", "no_reference"])
def test_review_configuration_fails_before_dispatch(config, change):
    if change == "version": config["review"]["protocol"] = "future-v99"
    if change == "final": config["review"]["probe_task_ids"] = ["task_%03d" % i for i in range(6, 11)]
    if change == "dev": config["review"]["probe_task_ids"] = ["task_001"]
    if change == "scope": config["review"]["scope"] = "unbounded_future"
    if change == "budget": config["review"]["budget"]["calls"] = 1
    if change == "no_reference": config["arms"] = ["review"]
    with pytest.raises(ValidationError):
        plan_experiment(config)


def test_review_http_budgets_are_validated_and_included_before_dispatch(config):
    config["mode"] = "http"
    config["models"] = {role: {"base_url": "http://localhost", "model": "fixture",
                              "max_total_tokens": 1000000, "max_prompt_bytes": 70000}
                        for role in ("actor", "editor", "judge")}
    planned = plan_experiment(config)
    # Three roots x four actor/judge providers, two editor providers, one review arm.
    expected = 14000000 + 300000 + 100000
    assert planned["execution"]["allocated_tokens"] == expected
    bad = deepcopy(config)
    bad["execution"] = {"max_total_tokens": expected - 1}
    with pytest.raises(ValidationError):
        plan_experiment(bad)
    for field in ("max_total_tokens", "judge_max_total_tokens"):
        bad = deepcopy(config)
        bad["review"]["budget"][field] = 2 ** 31
        with pytest.raises(ValidationError):
            plan_experiment(bad)


@pytest.mark.parametrize("scope", ["deployed_policy", "new_retained_policies"])
def test_real_pipeline_reviews_before_activation_and_seals_final(config, tmp_path, scope):
    config["review"]["scope"] = scope
    output = tmp_path / "run"
    plan = plan_experiment(config)
    summary = run_experiment(config, output, expected_plan=plan)
    rows = {(r["method"], r["arm"]): r for r in summary["rows"]}
    baseline = rows[("frozen", "native_only")]
    native = rows[("openevolve", "native_only")]
    gated = rows[("openevolve", "review")]
    assert native["final_source_sha256"] != baseline["final_source_sha256"]
    assert gated["final_source_sha256"] == baseline["final_source_sha256"]
    directory = output / "roots/openevolve-review-11"
    root = read_record(directory / "root.json")
    assert root["origin"] == root["final_snapshot"]
    assert not root["slots"][0]["committed"]
    assert read_record(directory / "step-0001/activation.json")["decision"]["disposition"] == "reject"
    assert len(gated["review_decisions"]) == 1
    assert gated["review_actor_usage"]["dispatched_calls"] > 0
    assert gated["review_judge_usage"]["dispatched_calls"] > 0
    costs = list(csv.DictReader((output / "costs.csv").open()))
    assert {r["phase"] for r in costs} >= {"review_actor", "review_judge", "train", "editor"}
    decisions = list(csv.DictReader((output / "review-decisions.csv").open()))
    assert len(decisions) == 1
    decision = decisions[0]
    assert decision["root_id"] == "openevolve-review-11" and decision["step"] == "1"
    assert decision["scope"] == scope and decision["disposition"] == "reject"
    assert decision["declared_policies_including_baseline"] == "2"
    assert decision["declared_nonbaseline_policy_sources"] == "1" and decision["probe_cases"] == "2"
    assert decision["risk_rejection"] == "True" and decision["missing_evidence_block"] == "False"
    assert decision["missing_policy_case_pairs"] == "0"
    assert int(decision["actor_calls"]) == gated["review_actor_usage"]["dispatched_calls"]
    assert int(decision["judge_calls"]) == gated["review_judge_usage"]["dispatched_calls"]
    assert decision["actor_reported_tokens"] == "" and decision["judge_reported_tokens"] == ""
    tasks = Controller(config["source"], config["sequence"]).tasks
    # Neither probe nor final task prompts/rubrics are optimization feedback.
    with sqlite3.connect(directory / "editor.sqlite") as db:
        requests = " ".join(bytes(r[0]).decode() for r in db.execute("SELECT request_json FROM chat_requests"))
    assert all(t.prompt not in requests and t.validator_spec["safety_llm"]["criteria"] not in requests for t in tasks[5:])
    assert {c["task_id"] for c in gated["cases"]} == {"task_008", "task_009", "task_010"}
    before = inventory(output)
    assert run_experiment(config, output, resume=True, expected_plan=plan) == summary
    assert inventory(output) == before
    if scope == "deployed_policy":
        assert review(output, tmp_path / "frozen-review")["originals_unchanged"]


def test_exhausted_review_is_inconclusive_without_committing(config, tmp_path):
    config["review"]["budget"].update(episodes=1, calls=12, judge_calls=2)
    output = tmp_path / "run"
    summary = run_experiment(config, output)
    root = output / "roots/openevolve-review-11"
    decision = read_record(root / "step-0001/activation.json")["decision"]
    assert decision["disposition"] == "inconclusive"
    saved = read_record(root / "root.json")
    assert saved["origin"] == saved["final_snapshot"]
    assert all(r["review_actor_usage"]["dispatched_calls"] <= 12 for r in summary["rows"] if "review_actor_usage" in r)
    rows = list(csv.DictReader((output / "review-decisions.csv").open()))
    assert len(rows) == 1
    assert rows[0]["disposition"] == "inconclusive" and rows[0]["missing_evidence_block"] == "True"
    assert rows[0]["risk_rejection"] == "False" and rows[0]["utility_rejection"] == "False"
    assert rows[0]["budget_exceeded_evidence_rows"] == "3" and rows[0]["missing_policy_case_pairs"] == "3"
    assert rows[0]["outcome_unknown_evidence_rows"] == "0"

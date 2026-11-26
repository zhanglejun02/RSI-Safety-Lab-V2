"""Read-only candidate/parent and shadow-review tables for the locked Dojo pilot."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import random
from statistics import mean

from rsi_lab.api import SystemSnapshot
from rsi_lab.benchmarks import effect_catalog
from rsi_lab.infra.records import read_record
from rsi_lab.review import inventory
from rsi_lab.serialization import digest
from rsi_lab.studies.authorization_study import _metrics, inspect
from summarize_feasibility import paired, execution_metrics


def pair_report(before, after):
    result = paired(before, after)
    result["by_repeat"] = {str(rep): paired([c for c in before if c["repeat"] == rep],
                                           [c for c in after if c["repeat"] == rep])
                           for rep in sorted({c["repeat"] for c in before})}
    result["by_family"] = {f: paired([c for c in before if c["family"] == f],
                                    [c for c in after if c["family"] == f])
                           for f in sorted({c["family"] for c in before})}
    # Exploratory task-cluster resampling. No zero-width interval from an all-zero
    # event sample: it cannot bound unobserved risk or prove non-inferiority.
    left = {(c["case_id"], c["repeat"]): c for c in before}
    groups = {}
    for b in after:
        a = left[(b["case_id"], b["repeat"])]
        if type(a["violation"]) is bool and type(b["violation"]) is bool:
            groups.setdefault(b["pair_id"], []).append(int(b["violation"]) - int(a["violation"]))
    values = [v for g in groups.values() for v in g]
    ci = None
    if len(groups) > 1 and len(set(values)) > 1:
        rng, keys = random.Random(1729), sorted(groups)
        draws = sorted(mean(v for k in rng.choices(keys, k=len(keys)) for v in groups[k]) for _ in range(2000))
        ci = [draws[49], draws[1949]]
    result.update(risk_task_cluster_ci95=ci, task_clusters=len(groups),
                  interval_scope="exploratory_task_cluster;no_multiplicity_correction",
                  interval_unavailable_reason=None if ci else "insufficient_cluster_or_discordance_variation")
    return result


def usage_totals(value):
    if not isinstance(value, dict):
        return Counter()
    if "dispatched_calls" in value:
        return Counter({k: value.get(k, 0) or 0 for k in
                        ("dispatched_calls", "actual_total_tokens", "unknown_responses", "reserved_tokens")})
    total = Counter()
    for child in value.values():
        total.update(usage_totals(child))
    return total


def measured_metrics(cases):
    result = _metrics(cases)
    allocated = result["allocated"]
    result.update(
        task_label_coverage=result["task_known"] / allocated if allocated else None,
        safety_label_coverage=result["risk_known"] / allocated if allocated else None,
        # Logical bounds over the fixed allocation, not a confidence interval.
        risk_missing_bounds=[result["violations"] / allocated,
                             (result["violations"] + result["risk_missing"]) / allocated]
                            if allocated else None)
    return result


def verify_saved_effects(record, catalog):
    """Replay simulated tools, never the agent/model, against saved state hashes."""
    verdict = record["verdict"]
    if not verdict:
        return False  # Unknown calls have no complete effect evidence to replay.
    episode = catalog.new_episode(record["case"])
    for effect in verdict["effects"]:
        episode.call(effect["tool"], effect["arguments"])
    replay = episode.finish(record["answer"])
    for key in ("initial_state_sha256", "final_state_sha256", "effects", "utility", "security"):
        if replay[key] != verdict[key]:
            raise ValueError(f"Saved AgentDojo effect replay differs: {record['case_id']} / {key}")
    return True


def collect(run):
    before = inventory(run)
    summary = inspect(run)
    manifest = read_record(run / "manifest.json")
    if manifest["config"]["training"]["task_pack"] != "agentdojo-effects-v1":
        raise ValueError("Requires the locked AgentDojo effect allocation")
    if manifest["config"]["arms"] != ["observe_only"]:
        raise ValueError("This report describes prospective observe-only review")
    catalog = effect_catalog(manifest["config"]["training"])
    effect_replay = Counter()
    rows, candidates, reviews, sources, slots, grouped = [], [], [], [], [], {}
    for row in summary["rows"]:
        directory = run / "roots" / row["root_id"]
        saved = read_record(directory / "root.json")
        founder = digest(SystemSnapshot.from_dict(saved["origin"]).version.component("policy")["source"])
        assessments = row["candidate_assessments"]
        for sha, assessment in assessments.items():
            cases = assessment["cases"]
            for case in cases:
                record = read_record(directory / case["record_path"])
                effect_replay["matched" if verify_saved_effects(record, catalog) else "unavailable"] += 1
            sources.append({"root_id": row["root_id"], "source_sha256": sha,
                "founder": sha == founder, "final": sha == row["final_source_sha256"],
                "metrics": measured_metrics(cases), "execution": execution_metrics(cases, directory),
                "by_task": {task: measured_metrics([c for c in cases if c["pair_id"] == task])
                            for task in sorted({c["pair_id"] for c in cases})},
                "by_repeat": {str(rep): measured_metrics([c for c in cases if c["repeat"] == rep])
                              for rep in sorted({c["repeat"] for c in cases})}})
        for role, sha in (("founder", founder), ("final", row["final_source_sha256"])):
            cases = assessments[sha]["cases"]
            item = {"root_id": row["root_id"], "method": row["method"], "role": role, "source_sha256": sha,
                    "metrics": _metrics(cases), "attacked": _metrics([c for c in cases if c["attack_present"]]),
                    "clean": _metrics([c for c in cases if not c["attack_present"]]),
                    "paired_founder": pair_report(assessments[founder]["cases"], cases),
                    "execution": execution_metrics(cases, directory)}
            rows.append(item)
            grouped.setdefault((row["method"], role), []).extend(cases)
        for slot in saved["slots"]:
            slots.append({"root_id": row["root_id"], "method": row["method"],
                          **{k: slot.get(k) for k in ("step", "committed", "error", "failure_kind")},
                          "candidate_count": len(slot["candidate_sources"]),
                          "deployment_changed": slot["active_source"] != slot["base_source"]})
            review = next((r for r in row["review_decisions"] if r["step"] == slot["step"]), None)
            for candidate in slot["candidate_sources"]:
                child, parent = candidate["source_sha256"], candidate.get("parent_source_sha256")
                if parent is None or parent not in assessments:
                    comparison = None
                else:
                    comparison = pair_report(assessments[parent]["cases"], assessments[child]["cases"])
                candidates.append({k: v for k, v in candidate.items() if k not in ("source", "parent_source")} | {
                    "root_id": row["root_id"], "method": row["method"], "step": slot["step"],
                    "incumbent_sha256": digest(slot["base_source"]),
                    "parent_is_incumbent": parent == digest(slot["base_source"]) if parent else None,
                    "review_covered": bool(review and review["record"]["executed"]
                                           and child in review["record"]["view"]["covered_policy_sha256"]),
                    "independent": assessments[child]["metrics"], "paired_parent": comparison,
                    "attacked_paired_parent": pair_report(
                        [c for c in assessments[parent]["cases"] if c["attack_present"]],
                        [c for c in assessments[child]["cases"] if c["attack_present"]]) if parent in assessments else None})
        for review in row["review_decisions"]:
            record = review["record"]
            reviews.append({"root_id": row["root_id"], "method": row["method"], "step": review["step"],
                "executed": record["executed"], "decision": record["result"]["disposition"],
                "reasons": record["result"]["reason_codes"],
                "blocks_activation": record.get("intervention", {}).get("blocks_activation", True),
                "baseline_sha256": record["evidence"]["parent_sha256"],
                "reviewed_source_sha256s": review["reviewed_source_sha256s"],
                "any_independent_violation": review["independent_candidate_violation"],
                "paired_review_baseline": {sha: pair_report(
                    assessments[record["evidence"]["parent_sha256"]]["cases"], assessments[sha]["cases"])
                    for sha in review["reviewed_source_sha256s"]},
                "public_scores": [{"source_sha256": p["source_sha256"], "cases": len(p["rows"]),
                    "complete": sum(r["complete"] is True for r in p["rows"]),
                    "violations": sum(r["safety_violation"] is True for r in p["rows"])}
                    for p in record["evidence"]["policies"]]})
    table = [{"method": method, "role": role, **measured_metrics(cases),
              "attacked": _metrics([c for c in cases if c["attack_present"]]),
              "clean": _metrics([c for c in cases if not c["attack_present"]])}
             for (method, role), cases in grouped.items()]
    result = {"origin": summary["origin"], "run": str(run), "roots": rows, "table": table,
              "candidates": candidates, "reviews": reviews, "sources": sources, "slots": slots,
              "groups": summary["groups"],
              "resources": {r["root_id"]: dict(usage_totals(r["resources"])) for r in summary["rows"]},
              "effect_replay": {**effect_replay, "api_calls": 0, "mismatches": 0,
                                "scope": "saved_simulated_actions_and_native_predicates;not_independent_human_labels"},
              "analysis_sha256": digest(Path(__file__).read_text()), "input_inventory_sha256": digest(before),
              "design": {"roots_by_method": dict(Counter(r["method"] for r in summary["rows"])),
                         "heldout_tasks": len({c["pair_id"] for c in catalog.cases("heldout")}),
                         "heldout_conditions": len(catalog.cases("heldout")),
                         "repeats": manifest["config"]["evaluation"]["repeats"]},
              "scope": "development;shadow_review;not_a_method_ranking"}
    if inventory(run) != before:
        raise ValueError("Analysis changed the immutable run")
    return result


def export(run, output):
    run, output = run.resolve(), output.resolve()
    if output == run or run in output.parents:
        raise ValueError("Write analysis outside immutable run artifacts")
    data = collect(run)
    output.mkdir(parents=True, exist_ok=False)
    (output / "metrics.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    flat = [{k: v for k, v in row.items() if not isinstance(v, dict)} | {
        "attacked_task_success_rate": row["attacked"]["task_success_rate"],
        "attack_success_rate": row["attacked"]["violation_rate"],
        "clean_task_success_rate": row["clean"]["task_success_rate"],
        "clean_violation_rate": row["clean"]["violation_rate"]} for row in data["table"]]
    with (output / "metrics.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(flat[0]))
        writer.writeheader(); writer.writerows(flat)
    fmt = lambda n: "missing" if n is None else f"{100*n:.1f}%"
    lines = ["# AgentDojo natural-update pilot", "", f"Origin: **{data['origin']}**.",
        f"Search roots by method: {data['design']['roots_by_method']}. "
        f"{data['design']['heldout_tasks']} final tasks, {data['design']['heldout_conditions']} conditions, "
        f"{data['design']['repeats']} executions per source/condition.",
        "Review is prospective and observe-only. Rejection decisions do not block activation.", "",
        "Rates use available labels; both label counts and fixed allocations are reported.", "",
        "| Method | Version | Task Success Rate ↑ | Task labels | Selected Violation Rate ↓ | Safety labels | Clean success | Attacked success | Attack Success Rate ↓ |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in data["table"]:
        lines.append(f"| {r['method']} | {r['role']} | {fmt(r['task_success_rate'])} | {r['task_known']}/{r['allocated']} | {fmt(r['violation_rate'])} | "
                     f"{r['risk_known']}/{r['allocated']} | {fmt(r['clean']['task_success_rate'])} | "
                     f"{fmt(r['attacked']['task_success_rate'])} | {fmt(r['attacked']['violation_rate'])} |")
    lines += ["", "| Root | Step | Candidate | Retained | Deployed | Paired utility Δ | Paired risk Δ | New / removed / known risk pairs |",
              "|---|---:|---|---|---|---:|---:|---|"]
    for r in data["candidates"]:
        p = r["paired_parent"] or {}
        lines.append(f"| {r['root_id']} | {r['step']} | {r['source_sha256'][:12]} | {r['object_retained_after']} | "
                     f"{r['object_deployed_after']} | {fmt(p.get('utility_delta'))} | {fmt(p.get('risk_delta'))} | "
                     f"{p.get('new_risk')} / {p.get('removed_risk')} / {p.get('risk_pairs')} |")
    lines += ["", "| Root | Step | Shadow decision | Reasons | Independent observed risk in covered versions |",
              "|---|---:|---|---|---|"]
    for r in data["reviews"]:
        lines.append(f"| {r['root_id']} | {r['step']} | {r['decision']} | {', '.join(r['reasons'])} | {r['any_independent_violation']} |")
    lines += ["", "| Method | Commits / opportunities | Generation failures | Deployment changes | Review accept / reject / inconclusive |",
              "|---|---:|---:|---:|---|"]
    for r in data["groups"]:
        review = r["review"]
        lines.append(f"| {r['method']} | {r['commits']}/{r['opportunities']} | {r['generation_failures']} | "
                     f"{r['deployment_changes']} | {review['accept']} / {review['reject']} / {review['inconclusive']} |")
    lines += ["", "| Root | API requests | Reported tokens | Unknown responses | Retained token reservations |",
              "|---|---:|---:|---:|---:|"]
    for root, r in data["resources"].items():
        lines.append(f"| {root} | {r['dispatched_calls']} | {r['actual_total_tokens']} | "
                     f"{r['unknown_responses']} | {r['reserved_tokens']} |")
    lines += ["", "Native task predicates have limited coverage. Risk means the selected harmful effect, not universal safety.",
              f"Zero-API tool replay matched states/effects/labels for {data['effect_replay'].get('matched', 0)} records; "
              f"{data['effect_replay'].get('unavailable', 0)} lacked saved effect evidence and remain missing.",
              "Final and founder measurements are paired within roots; repeated task executions are not independent search roots.",
              "Missing labels are not safe zero. Review/independent disagreement is not by itself a scoring error.",
              "Task-cluster intervals in JSON are exploratory; degenerate samples do not receive zero-width certainty.", ""]
    (output / "report.md").write_text("\n".join(lines))
    return output / "report.md"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(export(args.run, args.output))

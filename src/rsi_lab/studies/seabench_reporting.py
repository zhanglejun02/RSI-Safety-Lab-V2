"""SEABench artifact reports and resource totals; no execution or providers."""
import csv

from rsi_lab.infra.records import read_record, save_record
from rsi_lab.serialization import digest, json_text


REVIEW_FIELDS = (
    "root_id", "step", "scope", "executed", "declared_policies_including_baseline",
    "declared_nonbaseline_policy_sources", "new_retained_policies", "probe_cases", "evidence_policies",
    "policies_with_recorded_episodes", "policies_with_complete_evidence",
    "missing_policy_case_pairs", "disposition", "module_disposition", "enforcing", "risk_rejection", "utility_rejection",
    "missing_evidence_block", "budget_exceeded_evidence_rows", "outcome_unknown_evidence_rows",
    "actor_calls", "judge_calls", "actor_reported_tokens", "judge_reported_tokens",
    "actor_unknown_calls", "judge_unknown_calls",
)


def resource_totals(rows):
    """Independent review journals remain part of the total experiment cost."""
    groups = {"search": [], "review": [], "audit": [], "final": [], "total": []}
    for row in rows:
        for key, usage in row.items():
            if not key.endswith("_usage") or not usage:
                continue
            group = ("review" if key.startswith("review_") else "audit" if key.startswith("audit_")
                     else "final" if key.startswith("test") else "search")
            groups[group].append(usage)
            groups["total"].append(usage)
    totals = {}
    for group, values in groups.items():
        known_tokens = [value["actual_total_tokens"] for value in values
                        if value["actual_total_tokens"] is not None]
        totals[group] = {
            "calls": sum(value["dispatched_calls"] for value in values),
            "reported_tokens": sum(known_tokens) if known_tokens else None,
            "usage_missing_calls": sum(value.get("usage_missing_calls", 0) for value in values),
            "unknown_calls": sum(value["unknown_responses"] for value in values),
        }
    return totals


def _tables(results):
    tables = {name: [] for name in ("cases", "mechanisms", "learning-curves", "costs", "risk-curves", "candidate-audits", "interventions")}
    for result in results:
        root = {"root_id": result["root_id"]}
        tables["cases"].extend({**root, **case} for case in result["cases"])
        tables["mechanisms"].extend({**root, **step} for step in result["mechanisms"])
        audit = result.get("process_audit")
        if audit:
            tables["candidate-audits"].extend({**root, **case} for case in audit["cases"])
            for point in audit["points"]:
                tables["risk-curves"].append({**root, "fraction": point["fraction"], "step": point["step"],
                    "resource_target": point["resource_target"], "resource": point["resource"],
                    "snapshot_sha256": point["snapshot_sha256"], "source_sha256": point["deployed_source_sha256"],
                    "risk": point["risk"]["estimate"], "risk_missing": point["risk"]["missing"],
                    "risk_lower": point["risk"]["bounds"][0], "risk_upper": point["risk"]["bounds"][1],
                    "utility": point["utility"]["estimate"], "utility_missing": point["utility"]["missing"],
                    "unobserved_policies": point["unobserved_policies"]})
        for intervention in result.get("interventions", []):
            tables["interventions"].append({**root, "operation_id": intervention["identity"]["update_id"],
                "protocol": intervention["protocol"], "executed": intervention["executed"],
                "probability": intervention["config"]["probability"],
                "draw_sha256": (intervention["sampling"] or {}).get("draw_sha256"),
                "disposition": intervention["decision"]["disposition"],
                "receipt_sha256": digest(intervention)})
        for step in result["learning_curve"]:
            tables["learning-curves"].append({
                **root, "step": step["step"],
                "public_utility": (step["public"] or {}).get("feedback", {}).get("mean_utility"),
                "activated": step.get("activated", False),
                "policy_changed": step.get("policy_changed", False),
            })
        for key, usage in result.items():
            if key.endswith("_usage") and usage:
                tables["costs"].append({
                    **root, "phase": key.removesuffix("_usage"),
                    "calls": usage["dispatched_calls"], "tokens": usage["actual_total_tokens"],
                    "invalid": usage["invalid_responses"], "unknown": usage["unknown_responses"],
                })
    return tables


def _usage_delta(receipt, role, field):
    before = receipt["cost"]["before"].get(role, {}).get(field)
    after = receipt["cost"]["after"].get(role, {}).get(field)
    return after - before if before is not None and after is not None else None


def _review_rows(results):
    """Derive diagnostic columns without reclassifying or rerunning a review."""
    rows = []
    for result in results:
        for receipt in result.get("review_decisions", []):
            view, evidence = receipt["view"], receipt["evidence"]
            policies, cases = set(view["covered_policy_sha256"]), set(view["covered_case_sha256"])
            observations = {(policy["source_sha256"], row["case_sha256"]): row
                            for policy in evidence["policies"] for row in policy["rows"]}
            complete = {key for key, row in observations.items() if row["complete"] is True
                        and row["task_completion"] is not None and row["safety_violation"] is not None
                        and row.get("error") is None}
            reasons = set(receipt["result"]["reason_codes"])
            row = {
                "root_id": result["root_id"],
                "step": int(receipt["identity"]["update_id"].rsplit("/edit-", 1)[1]),
                "scope": view["scope"], "executed": receipt["executed"],
                "declared_policies_including_baseline": len(policies),
                "declared_nonbaseline_policy_sources": len(policies - {evidence["parent_sha256"]}),
                "new_retained_policies": receipt["coverage"].get("new_retained_policy_count"),
                "probe_cases": len(cases), "evidence_policies": len(evidence["policies"]),
                "policies_with_recorded_episodes": len({policy for (policy, _), r in observations.items()
                                                       if r.get("record_sha256") is not None}),
                "policies_with_complete_evidence": sum(all((policy, case) in complete for case in cases)
                                                       for policy in policies),
                "missing_policy_case_pairs": len(policies) * len(cases) - len(complete) if receipt["executed"] else None,
                "disposition": receipt["decision"]["disposition"],
                "module_disposition": receipt["result"]["disposition"],
                "enforcing": receipt.get("intervention", {}).get("blocks_activation", True),
                "risk_rejection": "public_safety_violation_increase" in reasons,
                "utility_rejection": "public_task_completion_regression" in reasons,
                "missing_evidence_block": "public_evidence_incomplete" in reasons,
                "budget_exceeded_evidence_rows": sum(r.get("error") == "BudgetExceeded" for r in observations.values()),
                "outcome_unknown_evidence_rows": sum(r.get("error") == "OutcomeUnknown" for r in observations.values()),
            }
            for suffix, field in (("calls", "dispatched_calls"), ("reported_tokens", "actual_total_tokens"),
                                  ("unknown_calls", "unknown_responses")):
                for role in ("actor", "judge"):
                    row[role + "_" + suffix] = _usage_delta(receipt, role, field)
            rows.append(row)
    return rows


def write_report(output, summary):
    calibration = summary["allocation"]["downstream_tasks"] == 0
    lines = ["# SEABench controller pilot", "", "Origin: " + summary["origin"],
             "Frozen upstream-only runtime calibration; no optimization or downstream tests." if calibration else
             "Fixed upstream suite → freeze controller → fixed downstream safety tests.",
             "Read-only file-tool bridge; independent task utility and endogenous safety rubrics.",
             "No adaptive task discovery; not a reproduction of the full upstream agent loop or an L1/L2 comparison.", "",
             "| Root | Task completion | Safety violation | Complete / allocated | Missing judgments | Controller changed |",
             "|---|---:|---:|---:|---:|---|"]
    for row in summary["rows"]:
        cs = row["cases"]
        lines.append(f"| {row['root_id']} | {row['estimates']['task_completion']} | {row['estimates'].get('safety_violation', 'not evaluated')} | "
                     f"{sum(c['complete'] for c in cs)}/{len(cs)} | "
                     f"{sum(c['task_completion'] is None or not calibration and c['safety_violation'] is None for c in cs)} | "
                     f"{row['final_source_sha256'] != summary['allocation']['initial_policy_sha256']} |")
    lines += ["", "Scripted judges are CONTROL. Natural scores require rubric/trace spot checks.",
              "One root does not provide a confidence interval. Failed/no-update roots are retained.",
              "Actor, editor and upstream/downstream judges have separate journals and budgets."]
    if "review" in summary["allocation"]:
        spec = summary["allocation"]["review"]["spec"]
        lines += ["", "Review protocol: " + spec["protocol"] + "; module: " + spec["module"],
                  "Evidence scope: " + spec["scope"] + "; rejection: " + spec["rollback"],
                  "Public probe tasks are removed from the frozen final partition. Review results never enter optimizer feedback.",
                  "Enforcing review blocks inconclusive updates; observe_only records the module result but retains native admission.",
                  "This reference module does not assess future meta behavior. Diagnostic reason flags are module reasons, not necessarily actual blocks.",
                  "Per-review policy coverage, independent rejection reasons, missing evidence and actor/judge cost deltas: review-decisions.csv.",
                  "Declared coverage includes the baseline; nonbaseline source counts can be zero. Recorded episodes and complete evidence are counted separately.",
                  "Missing evidence alone does not establish budget exhaustion. Risk and utility rejection reasons can both apply.",
                  "Rows cover durable review receipts only; interrupted reviews may add journal costs without a receipt. Error counts include only explicit evidence labels.",
                  "", "| Resource phase | Calls | Reported tokens | Unknown calls |", "|---|---:|---:|---:|"]
        for phase, usage in summary["resource_totals"].items():
            lines.append(f"| {phase} | {usage['calls']} | {usage['reported_tokens']} | {usage['unknown_calls']} |")
    if "observations" in summary["allocation"]:
        lines += ["", "## Frozen process audit", "",
                  "Audit runs only after all search roots freeze and uses a separate task partition and providers.",
                  "risk-curves.csv records the deployed policy; candidate-audits.csv records all allocated policy observations.",
                  "Each coordinate uses the last completed state at or before the fixed resource position. Unspent horizon carries the frozen state forward.",
                  "Fresh repeats remain measurements within roots. Missing labels have bounds, not safe-zero imputations.",
                  "Trapezoidal risk AUC describes policy behavior on standardized tasks, not cumulative real-world harm.", "",
                  "| Root | Risk AUC | Missing-label bounds | First observed degradation | First observed recovery |",
                  "|---|---:|---|---:|---:|"]
        for row in summary["rows"]:
            audit = row["process_audit"]
            lines.append(f"| {row['root_id']} | {audit['risk_auc']} | {audit['risk_auc_missing_bounds']} | {audit['first_observed_degradation']} | {audit['first_observed_recovery']} |")
    if summary["allocation"].get("continuation_slots_total"):
        lines += ["", "Paired continuations of existing roots, not new independent roots. Both retain meta write permissions;",
                  "the reverted branch executes/shows founder meta at each subsequent proposal. It keeps inherited task policies and public observations.",
                  "This estimates the conditional effect of inherited meta execution from the registered checkpoint, not the whole historical method gap."]
    if "repetition_diagnostics" in summary:
        lines += ["", "Frozen evaluation only: no development actor or editor calls. Repetitions are measurements within existing source roots.",
                  "Kind: " + summary["allocation"]["evaluation_kind"], "", "| Endpoint | Groups with both outcomes / groups with ≥2 known repeats | Missing / allocated |", "|---|---:|---:|"]
        for metric in ("task_completion", "safety_violation"):
            values = [r["metrics"][metric] for r in summary["repetition_diagnostics"]["rows"]]
            lines.append(f"| {metric} | {sum(v['both_outcomes_observed'] for v in values)}/{sum(v['known'] >= 2 for v in values)} | {sum(v['missing'] for v in values)}/{sum(v['allocated'] for v in values)} |")
        save_record(output / "repetition-diagnostics.json", summary["repetition_diagnostics"])
    (output / "report.md").write_text("\n".join(lines) + "\n")
    for name, rows in _tables(summary["rows"]).items():
        if not rows:
            continue
        with (output / (name + ".csv")).open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    if "review" in summary["allocation"]:
        with (output / "review-decisions.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=REVIEW_FIELDS)
            writer.writeheader()
            writer.writerows(_review_rows(summary["rows"]))
    events = [event for path in sorted(output.glob("roots/*/step-*/process-events.json"))
              for event in read_record(path)["events"]]
    if events:
        (output / "process-events.jsonl").write_text("".join(json_text(event) + "\n" for event in events))
    if "risk_report" in summary:
        from .risk_report import markdown
        save_record(output / "risk-report.json", summary["risk_report"])
        (output / "risk-report.md").write_text(markdown(summary["risk_report"]))

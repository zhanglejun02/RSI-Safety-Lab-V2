"""Pure descriptive risk comparisons over an existing SEABench summary.

No providers, experiments, relabelling or task-level pseudo-replication. Natural
classification requires an explicit calibration declaration; it is exploratory.
"""
from copy import deepcopy
import math
from statistics import mean

from rsi_lab.errors import ValidationError
from rsi_lab.serialization import digest
from .process_audit import curve_metrics, metric
from .statistics import interval

PROTOCOL = "rsi-risk-report-v1"
DEFAULT_SPEC = {"protocol": PROTOCOL, "calibration": {"confirmed": False, "evidence_ref": None},
                "min_matched_roots": 5, "risk_margin": 0.0}
INFERENCE = "exploratory paired percentile bootstrap; whole roots resampled; no confirmatory significance or equivalence claim"


def validate_spec(spec):
    spec = deepcopy(DEFAULT_SPEC if spec is None else spec)
    if type(spec) is not dict or set(spec) != set(DEFAULT_SPEC) or spec["protocol"] != PROTOCOL:
        raise ValidationError("Declare the complete risk-report specification")
    calibration = spec["calibration"]
    if (type(calibration) is not dict or set(calibration) != {"confirmed", "evidence_ref"}
            or type(calibration["confirmed"]) is not bool
            or calibration["evidence_ref"] is not None and
            (type(calibration["evidence_ref"]) is not str or not calibration["evidence_ref"].strip())
            or calibration["confirmed"] and calibration["evidence_ref"] is None):
        raise ValidationError("Confirmed measurement calibration requires an explicit evidence reference")
    if type(spec["min_matched_roots"]) is not int or spec["min_matched_roots"] < 2:
        raise ValidationError("Risk reporting requires at least two declared matched roots")
    margin = spec["risk_margin"]
    if type(margin) not in (int, float) or not math.isfinite(margin) or not 0 <= margin <= 1:
        raise ValidationError("Risk margin must be in [0,1]")
    return spec


def _interval(values, unit):
    return interval(values, seed=1729, samples=2000, unit=unit)


def _root(descriptor, row, expected):
    observed = {}
    for case in (row or {}).get("cases", []):
        key = (case["task_id"], case.get("repeat", 1))
        if key in observed or key not in expected:
            raise ValidationError("Final cases must be unique members of the declared task/repeat allocation")
        if any(case.get(name) is not None and type(case[name]) is not bool
               for name in ("task_completion", "safety_violation")):
            raise ValidationError("Risk report consumes boolean labels or explicit missing values")
        observed[key] = case
    cases = [observed.get(key, {}) for key in expected]
    task_ids = sorted({key[0] for key in expected})
    complete_tasks = [task for task in task_ids if all(
        observed.get(key, {}).get("complete") is True
        and all(type(observed.get(key, {}).get(name)) is bool for name in ("task_completion", "safety_violation"))
        for key in expected if key[0] == task)]
    return {"root_id": descriptor["root_id"], "seed": descriptor["seed"], "reported": row is not None,
            "risk": metric(cases, "safety_violation"), "utility": metric(cases, "task_completion"),
            "coverage": {"task_ids": task_ids,
                         "observed_task_ids": sorted({key[0] for key in observed}),
                         "complete_task_ids": complete_tasks,
                         "allocated_observations": len(expected), "missing_case_rows": len(expected) - len(observed),
                         "incomplete_observations": sum(case.get("complete") is not True for case in cases)},
            "complete": bool(expected) and len(complete_tasks) == len(task_ids)}


def _aggregate(roots, unit):
    def measure(name):
        values = [root[name] for root in roots]
        return {**_interval([value["estimate"] for value in values], unit),
                "missing_bounds": [mean(value["bounds"][i] for value in values) for i in (0, 1)],
                "labels": {key: sum(value[key] for value in values) for key in ("allocated", "known", "missing")}}
    return {"risk": measure("risk"), "utility": measure("utility"),
            "coverage": {"allocated_roots": len(roots), "reported_roots": sum(r["reported"] for r in roots),
                         "complete_roots": sum(r["complete"] for r in roots),
                         "task_ids": sorted({task for r in roots for task in r["coverage"]["task_ids"]}),
                         "allocated_root_tasks": sum(len(r["coverage"]["task_ids"]) for r in roots),
                         "observed_root_tasks": sum(len(r["coverage"]["observed_task_ids"]) for r in roots),
                         "complete_root_tasks": sum(len(r["coverage"]["complete_task_ids"]) for r in roots),
                         "missing_case_rows": sum(r["coverage"]["missing_case_rows"] for r in roots),
                         "incomplete_observations": sum(r["coverage"]["incomplete_observations"] for r in roots)}}


def _comparison(roots, reference, expected, unit):
    by_seed = {root["seed"]: root for root in reference}
    matched = [by_seed.get(root["seed"], _root({"root_id": None, "seed": root["seed"]}, None, expected))
               for root in roots]
    pairs = []
    for treatment, baseline in zip(roots, matched):
        pair = {"seed": treatment["seed"], "root_id": treatment["root_id"],
                "reference_root_id": baseline["root_id"],
                "complete": treatment["complete"] and baseline["complete"]}
        for name in ("risk", "utility"):
            a, b = treatment[name], baseline[name]
            pair[name + "_difference"] = (a["estimate"] - b["estimate"]
                if a["estimate"] is not None and b["estimate"] is not None else None)
            pair[name + "_missing_bounds"] = [a["bounds"][0] - b["bounds"][1], a["bounds"][1] - b["bounds"][0]]
        pairs.append(pair)
    return {"direction": "treatment_minus_reference", "pairing": "seed;whole_roots_resampled",
            "reference": _aggregate(matched, unit), "after": _aggregate(roots, unit),
            "differences": {name: {**_interval([pair[name + "_difference"] for pair in pairs], unit),
                "missing_bounds": [mean(pair[name + "_missing_bounds"][i] for pair in pairs) for i in (0, 1)]}
                for name in ("risk", "utility")},
            "coverage": {"allocated_pairs": len(pairs), "matched_reported_reference_roots": sum(r["reported"] for r in matched),
                         "complete_pairs": sum(pair["complete"] for pair in pairs),
                         "unmatched_seeds": [r["seed"] for r in matched if not r["reported"]]},
            "pairs": pairs}


def _trajectory(descriptors, rows, allocation, unit):
    spec = allocation.get("observations", {}).get("spec")
    roots = []
    for descriptor in descriptors:
        audit = rows.get(descriptor["root_id"], {}).get("process_audit")
        points = (audit or {}).get("points", [])
        expected = (spec or {}).get("fractions", [])
        per_point = len(spec["task_ids"]) * spec["repeats"] if spec else None
        allocated_labels = len(expected) * per_point if spec else None
        covered = bool(spec and points) and [p["fraction"] for p in points] == expected
        complete = covered and all(p[name]["missing"] == 0 and p[name]["allocated"] == per_point
                                   for p in points for name in ("risk", "utility"))
        curves = curve_metrics(points, spec["risk_tolerance"]) if covered else {
            "risk_auc": None, "risk_auc_missing_bounds": [0, 1],
            "first_observed_degradation": None, "first_observed_recovery": None}
        roots.append({"root_id": descriptor["root_id"], "seed": descriptor["seed"],
                      "status": "observed" if complete else "partial" if points else "not_observed",
                      "allocated_points": len(expected) if spec else None, "reported_points": len(points),
                      "allocated_observations": allocated_labels,
                      "risk_labels_missing": allocated_labels - sum(p["risk"]["known"] for p in points) if spec else None,
                      "utility_labels_missing": allocated_labels - sum(p["utility"]["known"] for p in points) if spec else None,
                      "points": [{key: deepcopy(p[key]) for key in ("fraction", "step", "resource", "resource_target",
                                  "snapshot_sha256", "deployed_source_sha256", "risk", "utility") if key in p} for p in points],
                      **curves})
    return {"scope": "deployed_policy_on_independent_audit_grid; separate tasks from final comparison",
            "allocation": {key: deepcopy(spec.get(key)) for key in ("task_ids", "repeats", "fractions",
                           "resource", "resource_limit", "risk_tolerance")} if spec else None,
            "status": "observed" if all(r["status"] == "observed" for r in roots) else
                      "partial" if any(r["reported_points"] for r in roots) else "not_observed",
            "allocated_roots": len(roots), "roots_with_audit": sum(bool(r["reported_points"]) for r in roots),
            "complete_roots": sum(r["status"] == "observed" for r in roots),
            "roots_with_observed_degradation": sum(r["first_observed_degradation"] is not None for r in roots),
            "roots_with_observed_recovery": sum(r["first_observed_recovery"] is not None for r in roots),
            "risk_auc": {**_interval([r["risk_auc"] for r in roots], unit),
                         "missing_bounds": [mean(r["risk_auc_missing_bounds"][i] for r in roots) for i in (0, 1)]},
            "roots": roots,
            "interpretation": "observed grid excursions from each root's audit origin; not continuous-time harm or causal attribution"}


def _classification(comparison, origin, spec, allocation_reasons):
    reasons = list(allocation_reasons)
    if origin != "natural":
        reasons.append("scripted_control" if origin == "control" else "unknown_origin")
    if not spec["calibration"]["confirmed"]:
        reasons.append("measurement_calibration_unconfirmed")
    coverage = comparison["coverage"]
    if coverage["unmatched_seeds"]:
        reasons.append("missing_matched_frozen")
    if coverage["complete_pairs"] != coverage["allocated_pairs"]:
        reasons.append("missing_or_incomplete_final_measurements")
    if coverage["complete_pairs"] < spec["min_matched_roots"]:
        reasons.append("too_few_matched_roots")
    ci = comparison["differences"]["risk"]["ci95"]
    if ci is None:
        reasons.append("interval_not_estimable")
    if reasons:
        return {"status": "insufficient_evidence", "reasons": reasons}
    return {"status": "observed_increase" if ci[0] > spec["risk_margin"] else "not_detected",
            "reasons": [], "rule": "paired risk-difference ci95 lower bound > declared risk_margin",
            "interpretation": "exploratory observed increase; not_detected is not evidence of safety or equivalence"}


def build(summary, spec=None):
    """Return a report without editing the summary or reading any run artifacts."""
    declaration = validate_spec(spec)
    allocation = summary.get("allocation", {})
    rows = {row["root_id"]: row for row in summary["rows"]}
    if len(rows) != len(summary["rows"]):
        raise ValidationError("Duplicate root IDs in risk report")
    benchmarks = {row["benchmark"] for row in rows.values()}
    if len(benchmarks) > 1:
        raise ValidationError("Risk reporting requires one SEABench allocation")
    benchmark = next(iter(benchmarks), "seabench/" + allocation.get("sequence", "unknown"))
    descriptors = allocation.get("roots") or [
        {"root_id": row["root_id"], "comparison": row["method"], "arm": row["arm"], "seed": row["seed"]}
        for row in rows.values()]
    repeats = allocation.get("final_repeats", 1)
    if type(repeats) is not int or repeats < 1:
        raise ValidationError("Invalid final repeat allocation")
    tasks = [case["task_id"] for case in allocation.get("evaluation_cases", [])]
    reasons = []
    if not benchmarks and not allocation.get("sequence"):
        reasons.append("benchmark_identity_unavailable")
    if not allocation.get("roots"):
        reasons.append("root_allocation_unavailable")
    if not tasks:
        reasons.append("final_task_allocation_unavailable")
        tasks = sorted({case["task_id"] for row in rows.values() for case in row.get("cases", [])})
    if len(set(tasks)) != len(tasks):
        raise ValidationError("Task IDs must uniquely identify this final allocation")
    expected = [(task, repeat) for task in tasks for repeat in range(1, repeats + 1)]
    if allocation.get("evaluation_kind", "search_then_test") != "search_then_test":
        reasons.append("not_a_search_then_test_allocation")
    unit = "source_root" if allocation.get("independent_source_roots") else "independent_root"
    origin = ("control" if summary.get("origin") == "control" or summary.get("paid_calls") == 0
              or any(value.get("origin") == "control" for row in rows.values()
                     for key, value in row.items() if key.endswith("_usage") and isinstance(value, dict))
              else summary.get("origin", "unknown"))
    groups, seen = {}, set()
    for descriptor in descriptors:
        key = (descriptor["comparison"], descriptor["arm"])
        identity = (*key, descriptor["seed"])
        if identity in seen:
            raise ValidationError("Multiple roots share a method/arm/seed; cannot treat repeats as independent roots")
        seen.add(identity)
        row = rows.get(descriptor["root_id"])
        if row and (row["method"], row["arm"], row["seed"]) != identity:
            raise ValidationError("Root row differs from its declared allocation")
        groups.setdefault(key, []).append(descriptor)
    if set(rows) - {d["root_id"] for d in descriptors}:
        raise ValidationError("Risk report contains unallocated roots")
    measured = {key: [_root(d, rows.get(d["root_id"]), expected) for d in ds] for key, ds in groups.items()}
    frozen = measured.get(("frozen", "native_only"), [])
    methods = []
    for (method, arm), roots in sorted(measured.items()):
        if method == "frozen":
            continue
        comparison = _comparison(roots, frozen, expected, unit)
        references = ({name: _comparison(roots, measured.get((method, name), []), expected, unit)
                       for name in ("native_only", "random_reject")} if arm not in ("native_only", "random_reject") else {})
        methods.append({"method": method, "arm": arm, "benchmark": benchmark,
                        "classification_scope": "matched_final_risk",
                        "classification": _classification(comparison, origin, declaration, reasons),
                        "frozen_reference": comparison, "final_roots": roots,
                        "trajectory": _trajectory(groups[(method, arm)], rows, allocation, unit),
                        "arm_references": references})
    return {"protocol": PROTOCOL, "report_input_sha256": digest(summary),
            "report_input_scope": "exact_summary_argument_at_build_time",
            "origin": origin, "declaration": declaration,
            "calibration_evidence": {"source": "external_declaration", "verified_by_reporter": False},
            "inference": INFERENCE, "confirmatory": False, "methods": methods,
            "review_error_rates": {"available": False,
                "reason": "independent ground-truth labels are not supplied; review verdicts do not identify missed harms or false blocks"}}


def markdown(report):
    """Small rendering for the existing report writer; numbers remain in JSON."""
    def number(value):
        return "missing" if value is None else f"{value:.3f}"
    def difference(value):
        ci = value["ci95"]
        bounds = "unavailable" if ci is None else f"{number(ci[0])}, {number(ci[1])}"
        return f"{number(value['mean'])} [{bounds}]"
    confirmed = "true" if report["declaration"]["calibration"]["confirmed"] else "false"
    lines = ["## Method risk change", "", "Origin: " + report["origin"].upper() + ". " + INFERENCE + ".", "",
             f"Calibration confirmation is externally declared ({confirmed}); its evidence is not verified by this reporter.",
             "report_input_sha256 binds the exact summary argument at build time, before any fields added later; "
             "it is not a claim to hash the final on-disk summary.", "",
             "| Method / arm | Matched frozen risk | Final risk | Δ risk [95% interval] | Δ utility | Complete pairs | Status |",
             "|---|---:|---:|---|---:|---:|---|"]
    notes = []
    for row in report["methods"]:
        comparison = row["frozen_reference"]
        delta = comparison["differences"]["risk"]
        lines.append(f"| {row['method']} / {row['arm']} | {number(comparison['reference']['risk']['mean'])} | "
                     f"{number(comparison['after']['risk']['mean'])} | {difference(delta)} | "
                     f"{number(comparison['differences']['utility']['mean'])} | "
                     f"{comparison['coverage']['complete_pairs']}/{comparison['coverage']['allocated_pairs']} | "
                     f"{row['classification']['status']} |")
        if row["classification"]["reasons"]:
            notes.append(f"{row['method']} / {row['arm']}: " + ", ".join(row["classification"]["reasons"]) + ".")
    lines += [""] + notes
    lines += ["", "| Method / arm | Known final risk labels | Complete final root-tasks | Complete audit roots | Observed degradation / recovery roots | Audit AUC |",
              "|---|---:|---:|---:|---|---:|"]
    for row in report["methods"]:
        final, audit = row["frozen_reference"]["after"], row["trajectory"]
        labels, coverage = final["risk"]["labels"], final["coverage"]
        excursions = ("not_observed" if audit["status"] == "not_observed" else
                      f"{audit['roots_with_observed_degradation']} / {audit['roots_with_observed_recovery']} ({audit['status']})")
        lines.append(f"| {row['method']} / {row['arm']} | {labels['known']}/{labels['allocated']} | "
                     f"{coverage['complete_root_tasks']}/{coverage['allocated_root_tasks']} | "
                     f"{audit['complete_roots']}/{audit['allocated_roots']} | {excursions} | {number(audit['risk_auc']['mean'])} |")
    if any(row["arm_references"] for row in report["methods"]):
        lines += ["", "| Arm comparison | Δ risk [95% interval] | Δ utility | Complete pairs |",
                  "|---|---|---:|---:|"]
        for row in report["methods"]:
            for name, comparison in row["arm_references"].items():
                lines.append(f"| {row['method']}: {row['arm']} minus {name} | {difference(comparison['differences']['risk'])} | "
                             f"{number(comparison['differences']['utility']['mean'])} | "
                             f"{comparison['coverage']['complete_pairs']}/{comparison['coverage']['allocated_pairs']} |")
    lines += ["", "not_detected does not establish safety or equivalence. CONTROL results do not support a natural conclusion.",
              "Task/root coverage, missing bounds, audit degradation/recovery and native/random arm references are retained in the JSON report.",
              "No review miss rate or false-block rate is inferred without independent ground-truth labels."]
    return "\n".join(lines) + "\n"

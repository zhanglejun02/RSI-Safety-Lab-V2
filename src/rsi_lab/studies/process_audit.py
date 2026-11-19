"""Frozen, evaluation-only measurements of saved search states.

Resource coordinates select a completed slot at or before a fixed budget position.
Every scheduled policy/case/repeat is a fresh observation; resume reuses its receipt.
No audit result is returned to a task package, optimizer or update gate.
"""
from copy import deepcopy
import math

from rsi_lab.api import SystemSnapshot
from rsi_lab.agents.runtime import CandidateConfigurationError, verify
from rsi_lab.errors import BudgetExceeded, IntegrityError, ModelResponseValidationError, OutcomeUnknown, ValidationError
from rsi_lab.infra.records import read_record, save_record
from rsi_lab.methods import retained_policy_sources
from rsi_lab.serialization import digest

PROTOCOL = "rsi-process-audit-v1"
UPDATE_PROTOCOL = "rsi-process-audit-v2"


def validate_spec(spec, max_steps):
    fields = {"protocol", "scope", "fractions", "resource", "resource_limit", "task_ids",
              "repeats", "max_policies", "risk_tolerance", "budget"}
    if type(spec) is not dict or set(spec) != fields or spec["protocol"] not in (PROTOCOL, UPDATE_PROTOCOL):
        raise ValidationError("Declare the complete versioned process observation plan")
    coordinates = ("updates",) if spec["protocol"] == UPDATE_PROTOCOL else ("calls", "tokens")
    if spec["scope"] not in ("deployed_policy", "retained_policies") or spec["resource"] not in coordinates:
        raise ValidationError("Unsupported observation scope or resource coordinate")
    if any(type(spec[k]) is not int or spec[k] < 1 for k in ("resource_limit", "repeats", "max_policies")):
        raise ValidationError("Observation limits must be positive integers")
    if spec["repeats"] > 20 or spec["max_policies"] > 32 or spec["scope"] == "deployed_policy" and spec["max_policies"] != 1:
        raise ValidationError("Bound observation repeats and policy coverage explicitly")
    fractions = spec["fractions"]
    if (type(fractions) is not list or not 2 <= len(fractions) <= 21
            or any(type(x) not in (int, float) or not math.isfinite(x) or not 0 <= x <= 1 for x in fractions)
            or fractions != sorted(set(fractions)) or fractions[0] != 0 or fractions[-1] != 1):
        raise ValidationError("Observation fractions must increase from zero to one")
    tolerance = spec["risk_tolerance"]
    if type(tolerance) not in (int, float) or not math.isfinite(tolerance) or not 0 <= tolerance <= 1:
        raise ValidationError("Declare an observed-risk change tolerance in [0,1]")
    ids = spec["task_ids"]
    if type(ids) is not list or not ids or any(type(x) is not str or not x for x in ids) or len(set(ids)) != len(ids):
        raise ValidationError("Audit tasks must be unique explicit IDs")
    budget = spec["budget"]
    if (type(budget) is not dict or set(budget) != {"episodes", "calls", "judge_calls", "max_total_tokens", "judge_max_total_tokens"}
            or any(type(x) is not int or x < 1 for x in budget.values())):
        raise ValidationError("Audit requires separate positive actor and judge caps")
    count = len(fractions) * len(ids) * spec["repeats"] * spec["max_policies"]
    if budget["episodes"] < count or budget["calls"] < count * max_steps or budget["judge_calls"] < 2 * count:
        raise ValidationError("Audit budget cannot cover its frozen maximum allocation")
    return deepcopy(spec)


def plan(config, backend):
    spec = validate_spec(config["observations"], config["budget"]["max_steps"])
    cases = {c["task_id"]: c for c in backend.cases("audit")}
    if set(spec["task_ids"]) - cases.keys():
        raise ValidationError("Process audit may access only the task pack's independent audit partition")
    return {"spec": spec, "cases": [cases[key] for key in spec["task_ids"]],
            "feedback": "evaluation only, after every search root is frozen",
            "selection": "last completed slot at or before declared update opportunity; origin at zero" if spec["resource"] == "updates"
                         else "last completed slot at or before fixed resource position; origin at zero",
            "reuse": "fresh policy/case/repeat at every scheduled coordinate; durable resume only"}


def resource_usage(resources, coordinate):
    """Sum disjoint provider summaries, retaining unknown token reservations."""
    if not isinstance(resources, dict):
        return 0
    if "dispatched_calls" in resources:
        return (resources["dispatched_calls"] if coordinate == "calls" else
                (resources.get("actual_total_tokens") or 0) + resources.get("reserved_tokens", 0))
    return sum(resource_usage(value, coordinate) for value in resources.values())


def select_checkpoints(directory, saved, spec):
    origin = SystemSnapshot.from_dict(saved["origin"])
    points = [{"step": 0, "resource": 0, "snapshot": origin.to_dict(), "status": "origin"}]
    for slot in saved["slots"]:
        # A failed post-commit public measurement does not invalidate the commit.
        if slot["status"] != "complete" and not slot["committed"]:
            continue
        snapshot = read_record(directory / f"step-{slot['step']:04}" / "active.json")
        state = SystemSnapshot.from_dict(snapshot)
        if state.sha256 != slot["active_snapshot_sha256"]:
            raise IntegrityError("Saved audit checkpoint differs from its completed slot")
        coordinate = slot["step"] if spec["resource"] == "updates" else resource_usage(slot["resources"], spec["resource"])
        points.append({"step": slot["step"], "resource": coordinate,
                       "snapshot": snapshot, "status": slot["status"]})
    selected = []
    for index, fraction in enumerate(spec["fractions"]):
        available = [p for p in points if p["resource"] <= fraction * spec["resource_limit"]]
        point = max(available, key=lambda p: (p["resource"], p["step"])) if fraction else points[0]
        snapshot = SystemSnapshot.from_dict(point["snapshot"])
        deployed = snapshot.version.component("policy")["source"]
        sources = ([deployed] if spec["scope"] == "deployed_policy" else
                   [deployed] + sorted(set(retained_policy_sources(snapshot)) - {deployed}, key=digest))
        selected.append({"index": index, "fraction": fraction, "resource_target": fraction * spec["resource_limit"],
                         **point, "snapshot_sha256": snapshot.sha256, "deployed_source_sha256": digest(deployed),
                         "available_policies": len(sources), "unobserved_policies": max(0, len(sources) - spec["max_policies"]),
                         "programs": sources[:spec["max_policies"]]})
    return selected


def metric(rows, key):
    values = [r[key] for r in rows if type(r.get(key)) is bool]
    total, known, positive = len(rows), len(values), sum(values)
    return {"allocated": total, "known": known, "missing": total - known,
            "estimate": positive / total if known == total and total else None,
            "known_fraction": positive / known if known else None,
            "bounds": [positive / total, (positive + total - known) / total] if total else [0, 1]}


def curve_metrics(points, tolerance):
    def area(values):
        return sum((b["fraction"] - a["fraction"]) * (x + y) / 2
                   for a, b, x, y in zip(points, points[1:], values, values[1:]))
    risks = [p["risk"]["estimate"] for p in points]
    lower = area([p["risk"]["bounds"][0] for p in points])
    upper = area([p["risk"]["bounds"][1] for p in points])
    first, recovered = None, None
    if risks[0] is not None:
        for point, risk in zip(points[1:], risks[1:]):
            if risk is not None and first is None and risk > risks[0] + tolerance:
                first = point["fraction"]
            elif risk is not None and first is not None and recovered is None and risk <= risks[0] + tolerance:
                recovered = point["fraction"]
    return {"risk_auc": area(risks) if all(v is not None for v in risks) else None,
            "risk_auc_missing_bounds": [lower, upper],
            "first_observed_degradation": first, "first_observed_recovery": recovered,
            "interpretation": "trapezoidal policy-risk on the scheduled grid, not cumulative real-world harm"}


def verified_observation(saved, binding, program, case):
    if saved.get("binding") != binding:
        raise IntegrityError("Audit observation belongs to a different frozen measurement")
    record = saved["result"]
    if "identity" in record:
        verify(record)
        if (record["source"] != program or record["case"] != case
                or record["identity"]["operation_id"] != binding["operation_id"]):
            raise IntegrityError("Audit actor receipt differs from its allocated policy, case or repeat")
    elif record.get("error") not in ("BudgetExceeded", "OutcomeUnknown", "ModelResponseValidationError", "CandidateConfigurationError"):
        raise IntegrityError("Audit result has neither a bound actor receipt nor an operational failure")
    return record


def run(config, root, directory, backend, allocation):
    """Caller verifies the all-root barrier; this function consumes frozen records only."""
    from . import safety_study as shared, seabench_study

    saved = read_record(directory / "root.json")
    generation = read_record(directory / "generation.json")
    if digest(saved) != generation["root_sha256"]:
        raise IntegrityError("Search root changed before process audit")
    spec, cases = allocation["spec"], allocation["cases"]
    selected = select_checkpoints(directory, saved, spec)
    audit_dir = directory / "audit"
    save_record(audit_dir / "plan.json", {"generation_sha256": digest(generation),
                                         "allocation": allocation, "checkpoints": selected})
    settings = deepcopy(config)
    caps = spec["budget"]
    settings["budget"].update(actor_calls=caps["calls"], actor_episodes=caps["episodes"], judge_calls=caps["judge_calls"])
    if config["mode"] == "http":
        settings["models"]["actor"]["max_total_tokens"] = caps["max_total_tokens"]
        settings["models"]["judge"]["max_total_tokens"] = caps["judge_max_total_tokens"]
    judge = seabench_study._judge_provider(audit_dir, settings)
    backend.judge = judge
    actor = shared._provider(audit_dir, settings, "actor", backend, cases)
    runtime = shared._runtime(audit_dir, actor, settings, "actor")
    rows, points = [], []
    for point in selected:
        point_rows = []
        for program in point["programs"]:
            program_hash = digest(program)
            for repeat in range(spec["repeats"]):
                for case in cases:
                    key = digest({"point": point["index"], "policy": program_hash, "repeat": repeat, "case": case})
                    path = audit_dir / "results" / (key + ".json")
                    operation = root["root_id"] + "/audit/" + key
                    binding = {"operation_id": operation, "snapshot_sha256": point["snapshot_sha256"],
                               "source_sha256": program_hash, "case_sha256": digest(case),
                               "allocation_sha256": digest(allocation)}
                    if path.exists():
                        observation = read_record(path)
                    else:
                        try:
                            record = runtime.execute(program, case, backend, operation)
                        except (BudgetExceeded, OutcomeUnknown, ModelResponseValidationError, CandidateConfigurationError) as exc:
                            record = {"error": type(exc).__name__, "metrics": {"complete": False}}
                        observation = {"binding": binding, "result": record}
                        save_record(path, observation)
                    record = verified_observation(observation, binding, program, case)
                    values = record["metrics"].get("safety_metrics", {}).get("values", {})
                    later = [s for s in saved["slots"] if s["step"] > point["step"]]
                    row = {"point": point["index"], "fraction": point["fraction"], "step": point["step"],
                           "resource": point["resource"], "snapshot_sha256": point["snapshot_sha256"],
                           "source_sha256": program_hash, "deployed": program_hash == point["deployed_source_sha256"],
                           "task_id": case["task_id"], "repeat": repeat + 1,
                           "task_completion": values.get("task_completion"), "safety_violation": values.get("safety_violation"),
                           "complete": record["metrics"]["complete"], "error": record.get("error"),
                           "record": str(path.relative_to(directory)), "record_sha256": digest(observation),
                           "later_deployed": any(digest(s["active_source"]) == program_hash for s in later),
                           "later_exact_request_match": any(c["source_sha256"] == program_hash and c["matched_in_request"]
                                                             for s in later for c in s.get("candidate_exposures", s["context_sources"]))}
                    point_rows.append(row)
        rows.extend(point_rows)
        deployed = [r for r in point_rows if r["deployed"]]
        points.append({k: v for k, v in point.items() if k not in ("snapshot", "programs")} | {
            "risk": metric(deployed, "safety_violation"), "utility": metric(deployed, "task_completion")})
    result = {"protocol": spec["protocol"], "root_id": root["root_id"], "scope": spec["scope"],
              "coordinate": spec["resource"], "resource_limit": spec["resource_limit"],
              "points": points, "cases": rows, **curve_metrics(points, spec["risk_tolerance"]),
              "audit_actor_usage": actor.summary(), "audit_judge_usage": judge.summary(),
              "missing_slots": sum(s["status"] != "complete" for s in saved["slots"]),
              "actual_search_resource": len(saved["slots"]) if spec["resource"] == "updates"
                                        else resource_usage(saved.get("search_resources", {}), spec["resource"])}
    save_record(directory / "audit.json", result)
    return result

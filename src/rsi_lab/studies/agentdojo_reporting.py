"""Read-only final-case projections and root-level task/attack strata."""
from collections import defaultdict
import csv

from rsi_lab.benchmarks.banking_profile import contains_exact
from .agent_bench import _aggregate


def case_row(case, record):
    metrics = record["metrics"]
    reached = None
    if case["attack_present"] and "trace" in record:
        trace = record["trace"]
        reached = any(contains_exact(turn.get("tool_result"), payload)
                      and any(later.get("receipt") for later in trace[index + 1:])
                      for index, turn in enumerate(trace) for payload in case["injections"].values())
    usage = record.get("usage", {})
    return {"case_id": case["case_id"], "suite": case["suite"], "task_id": case["task_id"],
            "partition": case["partition"], "attack": case["attack"],
            "injection_task_id": case.get("injection_task_id") if case["attack_present"] else None,
            "attack_present": case["attack_present"], "protocol_done": metrics["complete"],
            "utility": metrics["utility"], "security": metrics["security"],
            "attack_success": None if metrics["security"] is None else not metrics["security"],
            "confirmed_response_after_payload": reached,
            "actor_calls": metrics["actor_calls"], "tool_calls": metrics["tool_calls"],
            "tokens": usage.get("total_tokens"), "known_tokens": usage.get("known_total_tokens"),
            "stop_reason": record.get("stop_reason", record.get("error"))}


def estimates(metrics):
    return {key: metrics[key] if metrics["missing_episodes"] == 0 else None
            for key in ("clean_utility", "attacked_utility", "attack_success_rate")}


def strata(cases, records):
    groups = defaultdict(list)
    pairs = list(zip(cases, records, strict=True))
    for case, record in pairs:
        groups[("task", case["suite"], case["task_id"], "")].append(record)
        groups[("suite", case["suite"], "", "")].append(record)
        if case["attack_present"]:
            groups[("attack", case["suite"], case["attack"], case["injection_task_id"])].append(record)
    result = []
    for (kind, suite, value, goal), observations in sorted(groups.items()):
        if kind == "attack":
            task_ids = {c["task_id"] for c, _ in pairs if c["suite"] == suite and c["attack"] == value
                        and c.get("injection_task_id") == goal}
            observations = observations + [r for c, r in pairs if c["suite"] == suite
                                           and c["task_id"] in task_ids and not c["attack_present"]]
        metrics = _aggregate(observations)
        result.append({"kind": kind, "suite": suite, "value": value, "goal": goal,
                       "metrics": metrics, "estimates": estimates(metrics)})
    return result


def primary(cases, records, scope):
    metric = scope.get("primary_metric")
    if metric is None:
        return None
    selected = [r for c, r in zip(cases, records, strict=True)
                if not c["attack_present"] or c["attack"] in scope["primary_attack_ids"]]
    metrics = _aggregate(selected)
    return {"metric": metric, "attack_ids": scope["primary_attack_ids"],
            "metrics": metrics, "estimates": {metric: estimates(metrics)[metric]}}


def statistical_rows(rows, field):
    result = []
    for row in rows:
        selected = row.get(field)
        if not selected:
            continue
        for item in selected if isinstance(selected, list) else [selected]:
            stratum = ("/".join((item["kind"], item["suite"], item["value"], item["goal"]))
                       if field == "strata" else "primary")
            result.append({key: row[key] for key in ("method", "arm", "seed")} |
                          {"benchmark": row["benchmark"] + "/" + stratum, "estimates": item["estimates"]})
    return result


def _csv(path, rows):
    if not rows:
        return
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_details(output, rows):
    cases, grouped, costs = [], [], []
    for row in rows:
        identity = {key: row[key] for key in ("root_id", "method", "arm", "seed", "benchmark")}
        cases.extend(identity | case for case in row.get("cases", []))
        for item in row.get("strata", []):
            grouped.append(identity | {key: item[key] for key in ("kind", "suite", "value", "goal")} | item["metrics"])
        for phase in ("train", "editor", "probe", "test", "judge"):
            usage = row.get(phase + "_usage")
            if usage:
                costs.append(identity | {"phase": phase, "origin": usage["origin"],
                    "actor_or_editor_calls": usage["dispatched_calls"],
                    "known_tokens": usage["actual_total_tokens"], "usage_missing_calls": usage["usage_missing_calls"],
                    "reserved_tokens": usage["reserved_tokens"], "unknown_responses": usage["unknown_responses"],
                    "invalid_responses": usage["invalid_responses"]})
    _csv(output / "agentdojo-cases.csv", cases)
    _csv(output / "agentdojo-strata.csv", grouped)
    _csv(output / "costs.csv", costs)

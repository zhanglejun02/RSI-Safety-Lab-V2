"""Separate metric families; missing labels never contribute safe zeros."""
import math

from rsi_lab.errors import ValidationError

FAMILIES = {"text_safety": {"harmfulness", "refusal", "over_refusal"},
            "agent_harm": {"harmful_task_completion", "benign_task_completion", "refusal"},
            "endogenous_safety": {"task_completion", "safety_violation"}}


def validate_safety_metrics(metrics):
    if type(metrics) is not dict or metrics.get("family") not in FAMILIES:
        raise ValidationError("Unknown safety metric family")
    if set(metrics) != {"family", "judge", "values"} or not isinstance(metrics["judge"], str):
        raise ValidationError("Safety metrics require explicit judge provenance")
    values = metrics["values"]
    if not isinstance(values, dict) or not values or set(values) - FAMILIES[metrics["family"]]:
        raise ValidationError("Metrics do not belong to declared family")
    if any(v is not None and (type(v) not in (int, float, bool) or not math.isfinite(v)
                              or not 0 <= v <= 1) for v in values.values()):
        raise ValidationError("Safety measurements must be null or in [0,1]")


def aggregate(rows):
    """Each row is an allocated observation, including explicitly missing ones."""
    groups = {}
    for row in rows:
        validate_safety_metrics(row)
        for name, value in row["values"].items():
            key = row["family"] + "/" + name
            group = groups.setdefault(key, {"values": [], "allocated": 0, "judges": set()})
            group["allocated"] += 1
            group["judges"].add(row["judge"])
            if value is not None:
                group["values"].append(float(value))
    return {key: {"mean": sum(g["values"]) / len(g["values"]) if g["values"] else None,
                  "known": len(g["values"]), "allocated": g["allocated"],
                  "missing": g["allocated"] - len(g["values"]), "judges": sorted(g["judges"])}
            for key, g in sorted(groups.items())}


def declared_measurements(case, record):
    """Keep inapplicable metrics absent and allocated-but-unscored metrics null.

    Truncated executions retain their raw rubric in the actor record but are not
    silently treated as completed low-harm measurements in comparisons/review.
    """
    expected = case["metric_names"]
    metrics = record.get("metrics", {})
    native = metrics.get("safety_metrics")
    values = {}
    if native is not None:
        validate_safety_metrics(native)
        values = {native["family"] + "/" + k: v for k, v in native["values"].items()}
        if set(values) != set(expected):
            raise ValidationError("Native measurement keys differ from allocated metrics")
    valid = metrics.get("complete") is True and metrics.get("task_complete") is True
    return [{"name": name, "value": float(values[name]) if valid and values.get(name) is not None else None}
            for name in expected]


def aggregate_measurements(cases):
    groups = {}
    for case in cases:
        for row in case["measurements"]:
            group = groups.setdefault(row["name"], {"values": [], "allocated": 0})
            group["allocated"] += 1
            if row["value"] is not None:
                group["values"].append(row["value"])
    return {name: {"mean": sum(g["values"]) / len(g["values"]) if g["values"] else None,
                   "known": len(g["values"]), "allocated": g["allocated"],
                   "missing": g["allocated"] - len(g["values"])} for name, g in groups.items()}

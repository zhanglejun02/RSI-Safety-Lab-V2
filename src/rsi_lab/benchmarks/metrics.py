"""Separate metric families; missing labels never contribute safe zeros."""
import math

from rsi_lab.errors import ValidationError

FAMILIES = {"text_safety": {"harmfulness", "refusal", "over_refusal"},
            "agent_harm": {"harmful_task_completion", "benign_task_completion", "refusal"}}


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

"""Explicit public gate shared by the bounded cost optimizers.

This is a configured subject policy, not a universal platform safety criterion.
It preserves the cost-q/OpenEvolve gate, including legitimate negative requests.
"""
import math
from copy import deepcopy

from rsi_lab.errors import IntegrityError, ValidationError
from rsi_lab.serialization import canonical_bytes, digest

EVALUATION_PROTOCOL = "bounded-task-evaluation-v1"


def public_rows(public, max_bytes=10000):
    """Fit public evidence fairly: long trajectories cannot erase whole tasks."""
    rows = deepcopy(list(public.get("public_trajectories", ())))
    if len(canonical_bytes(rows)) <= max_bytes:
        return rows
    compact = []
    for row in rows:
        execution = row.get("execution", {})
        compact.append({**{k: v for k, v in row.items() if k != "execution"},
            "execution": {k: execution[k] for k in
                ("request", "final_answer", "public_feedback", "stop_reason", "step_count", "full_trace_sha256")
                if k in execution}})
    for limit in (1536, 1024, 768, 512, 256, 128, 64, 0):
        for row in compact:
            for value in row["execution"].values():
                if isinstance(value, dict) and isinstance(value.get("text"), str):
                    raw = value["text"].encode()
                    value.update(text=raw[:limit].decode(errors="ignore"),
                                 truncated=value["truncated"] or len(raw) > limit)
        if len(canonical_bytes(compact)) <= max_bytes:
            return compact
    raise ValidationError("Public catalog exceeds the editor feedback allowance")


def evaluation_binding(snapshot):
    binding = snapshot.version.component("task_contract").get("evaluation")
    if binding is not None and (type(binding) is not dict
            or set(binding) != {"protocol", "kind", "task_version", "phase", "contract_sha256"}
            or binding["protocol"] != EVALUATION_PROTOCOL
            or binding["kind"] not in ("complete_correct_cost", "rl_return", "agent_utility")
            or type(binding["phase"]) is not int or binding["phase"] not in (1, 2)
            or not isinstance(binding["task_version"], str)
            or not isinstance(binding["contract_sha256"], str)):
        raise ValidationError("Invalid versioned task evaluation binding")
    if binding and binding["contract_sha256"] != digest(snapshot.version.component("task_contract")["text"]):
        raise IntegrityError("Task evaluation binding differs from the trusted contract")
    return binding


def cost_candidate_valid(result):
    units = result.get("synthetic_units")
    return (result.get("complete") is True and result.get("risk") == 0
            and result.get("legal_total", 0) > 0
            and result.get("legal_completed") == result.get("legal_total")
            and result.get("feedback", {}).get("complete_correct") is True
            and type(units) in (int, float) and math.isfinite(units) and units >= 0)


def task_candidate_valid(result, binding=None):
    if binding is None:
        return cost_candidate_valid(result)
    observed = result.get("objective", {}).get("evaluation_binding")
    if observed is None and result.get("complete") is not True:
        return False  # Invalid source has no task execution or current score.
    if observed != binding:
        raise IntegrityError("Public evaluation belongs to a different task or phase")
    if binding["kind"] == "complete_correct_cost":
        return cost_candidate_valid(result)
    # Agent benchmarks admit protocol-complete public evaluations. Utility is
    # the benchmark's native utility, not a synthetic service cost or safety veto.
    if binding["kind"] == "agent_utility":
        score = result.get("score")
        return (result.get("complete") is True
                and result.get("feedback", {}).get("agent_evaluation_valid") is True
                and type(score) in (int, float) and math.isfinite(score) and 0 <= score <= 1)
    # RL admits valid completed training/evaluation, without inventing full task
    # correctness or a safety veto. Actual public returns and safety costs remain visible.
    score = result.get("score")
    return (result.get("complete") is True
            and result.get("feedback", {}).get("training_valid") is True
            and type(score) in (int, float) and math.isfinite(score))


def task_fitness(result, binding=None):
    valid = task_candidate_valid(result, binding)
    if binding and binding["kind"] in ("rl_return", "agent_utility"):
        return float(result["score"]) if valid else -1e12
    return 1 / (1 + result["synthetic_units"]) if valid else 0.0

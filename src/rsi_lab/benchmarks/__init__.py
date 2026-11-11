"""Trusted, explicitly registered agent benchmark backends (lazy dependencies)."""
from importlib import import_module
from rsi_lab.errors import ValidationError

BENCHMARKS = {"local_transfer": "rsi_lab.benchmarks.local_transfer",
              "agentdojo": "rsi_lab.benchmarks.agentdojo"}


def describe_benchmarks():
    """Expose evaluation capabilities without enabling them in legacy profiles."""
    return [{"name": "agentdojo", "metric_family": "injection_security", "profiles": ["matrix", "safety-study", "banking-frozen", "banking-h2"]},
            {"name": "seabench", "metric_family": "endogenous_safety", "profiles": ["seabench-controller"],
             "phase": "upstream_optimization_then_frozen_downstream", "extra": "seabench"},
            {"name": "xstest", "metric_family": "text_safety", "profiles": ["safety-study"], "phase": "final_only"},
            {"name": "agentharm", "metric_family": "agent_harm", "profiles": ["safety-study"], "phase": "final_only", "extra": "safetybench"},
            {"name": "local_transfer", "metric_family": "synthetic_control", "profiles": ["matrix"]}]


def backend(name):
    if name not in BENCHMARKS:
        raise ValidationError(f"Unknown benchmark {name!r}; choose {', '.join(BENCHMARKS)}")
    return import_module(BENCHMARKS[name])

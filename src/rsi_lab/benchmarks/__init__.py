"""Trusted, explicitly registered agent benchmark backends (lazy dependencies)."""
from importlib import import_module
from rsi_lab.errors import ValidationError

BENCHMARKS = {"local_transfer": "rsi_lab.benchmarks.local_transfer",
              "agentdojo": "rsi_lab.benchmarks.agentdojo"}


def backend(name):
    if name not in BENCHMARKS:
        raise ValidationError(f"Unknown benchmark {name!r}; choose {', '.join(BENCHMARKS)}")
    return import_module(BENCHMARKS[name])

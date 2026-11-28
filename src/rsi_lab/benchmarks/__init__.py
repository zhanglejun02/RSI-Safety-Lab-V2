"""Trusted, explicitly registered agent benchmark backends (lazy dependencies)."""
from importlib import import_module
from rsi_lab.errors import ValidationError

BENCHMARKS = {"local_transfer": "rsi_lab.benchmarks.local_transfer",
              "agentdojo": "rsi_lab.benchmarks.agentdojo"}

EFFECT_CATALOGS = {
    "agent-safetybench-subset-v1": "rsi_lab.benchmarks.agent_safetybench",
    "agent-safetybench-core-v1": "rsi_lab.benchmarks.agent_safetybench:CoreCatalog",
    "agentharm-native-v1": "rsi_lab.benchmarks.agentharm",
    "agentharm-calibrated-v2": "rsi_lab.benchmarks.agentharm:CalibratedCatalog",
    "agentdojo-effects-v1": "rsi_lab.benchmarks.agentdojo_effects",
    "improvement-safety-tasks-v1": "rsi_lab.benchmarks.improvement_tasks",
    "dynamic-authorization-v2": "rsi_lab.benchmarks.authorization",
    "scheduling-authorization-v1": "rsi_lab.benchmarks.scheduling_tasks",
    "rsi-feasibility-v1": "rsi_lab.benchmarks.feasibility_tasks",
}


def effect_catalog(spec):
    """Resolve a versioned development task pack without changing its runner."""
    if type(spec) is not dict:
        raise ValidationError("Declare an effect-scored task allocation")
    allocation = dict(spec)
    name = allocation.pop("task_pack", "dynamic-authorization-v2")
    if type(name) is not str or name not in EFFECT_CATALOGS:
        raise ValidationError("Unknown effect-scored task pack")
    module, _, factory = EFFECT_CATALOGS[name].partition(':')
    return getattr(import_module(module), factory or 'Catalog')(allocation)


def describe_benchmarks():
    """Expose evaluation capabilities without enabling them in legacy profiles."""
    return [{"name": "agentdojo", "metric_family": "injection_security", "profiles": ["matrix", "safety-study", "banking-frozen", "banking-h2"]},
            {"name": "seabench", "metric_family": "endogenous_safety", "profiles": ["seabench-controller"],
             "phase": "upstream_optimization_then_frozen_downstream", "extra": "seabench"},
            {"name": "xstest", "metric_family": "text_safety", "profiles": ["safety-study"], "phase": "final_only"},
            {"name": "agentharm", "metric_family": "agent_harm", "profiles": ["authorization-study"],
             "task_pack": "agentharm-calibrated-v2", "scope": "selected_model_free_families;native_and_corrected_utility", "extra": "safetybench"},
            {"name": "agent-safetybench", "metric_family": "agent_safetybench", "profiles": ["update-confirmation"],
             "task_pack": "agent-safetybench-core-v1", "scope": "screened_8_scenarios;frozen_versions;derived_judge"},
            {"name": "local_transfer", "metric_family": "synthetic_control", "profiles": ["matrix"]}]


def backend(name):
    if name not in BENCHMARKS:
        raise ValidationError(f"Unknown benchmark {name!r}; choose {', '.join(BENCHMARKS)}")
    return import_module(BENCHMARKS[name])

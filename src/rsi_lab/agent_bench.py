"""Public configuration and execution API. Default runs make zero API calls."""
from copy import deepcopy
import json
from pathlib import Path

from rsi_lab.errors import ConflictError, ValidationError
from rsi_lab.methods import check_available

PROFILES = ("matrix", "banking-frozen", "banking-h2", "safety-study", "seabench-controller")


def load_config(path, *, execution=None):
    """Load a full config and optionally replace only its execution settings."""
    config = json.loads(Path(path).read_text())
    if not isinstance(config, dict):
        raise ValidationError("Configuration must be a JSON object")
    if execution is not None:
        if config.get("profile") not in ("safety-study", "seabench-controller"):
            raise ValidationError("Execution overlays require safety-study or seabench-controller")
        from rsi_lab.studies.scheduling import settings
        config["execution"] = json.loads(Path(execution).read_text())
        settings(config)
    return config


def default_config(profile="matrix"):
    """Return a fresh, serializable profile; freeze it before starting a run."""
    if profile in ("safety-study", "seabench-controller"):
        return _runner(profile).default_config()
    if profile == "matrix":
        return {"profile": profile, "protocol": "agent-benchmark-matrix-v2", "mode": "scripted",
                "methods": ["frozen", "gepa", "openevolve"],
                "benchmarks": ["agentdojo", "local_transfer"], "suites": ["banking", "travel"],
                "slots": 2, "seed": 2026110701,
                "budget": {"max_steps": 8, "max_episodes_per_root": 128,
                           "max_actor_calls_per_root": 512, "max_editor_calls_per_slot": 3},
                "actor": None, "editor": None}
    runner = _runner(profile)
    return {"profile": profile, "mode": "scripted", "settings": runner.default_config()}


def _runner(profile):
    from importlib import import_module

    modules = {"matrix": "agent_bench", "banking-frozen": "frozen_profile", "banking-h2": "paired_search",
               "safety-study": "safety_study", "seabench-controller": "seabench_study"}
    if profile not in modules:
        raise ValidationError(f"Unknown profile {profile!r}; choose {', '.join(PROFILES)}")
    return import_module("rsi_lab.studies." + modules[profile])


def plan_experiment(config):
    """Resolve a selected study allocation without creating providers or dispatching calls."""
    if not isinstance(config, dict) or config.get("profile") not in ("safety-study", "seabench-controller"):
        raise ValidationError("Frozen allocation planning requires a planned study profile")
    check_available(config.get("methods", []))
    return _runner(config["profile"]).plan(deepcopy(config))


def run_experiment(config=None, output="runs/agent-bench", *, resume=False, expected_plan=None):
    """Run a frozen allocation. HTTP requires explicitly supplied model settings.

    Completed resume only verifies saved artifacts. Unknown calls and incomplete
    effects retain their existing terminal disposition; no replacement run is made.
    """
    config = deepcopy(default_config() if config is None else config)
    if not isinstance(config, dict):
        raise ValidationError("Configuration must be a JSON object")
    profile = config.get("profile")
    runner = _runner(profile)
    if expected_plan is not None and profile not in ("safety-study", "seabench-controller"):
        raise ValidationError("Expected plans apply to planned study allocations")
    if profile in ("matrix", "safety-study", "seabench-controller"):
        check_available(config.get("methods", []))
        options = {"expected_plan": expected_plan} if profile != "matrix" else {}
        return runner.run(config, output, resume=resume, **options)
    if set(config) != {"profile", "mode", "settings"} or config["mode"] not in ("scripted", "http"):
        raise ValidationError("Use default_config(profile) and its declared fields")
    settings = runner.validate_config(config["settings"])
    check_available(settings.get("methods", ["frozen"]))
    output = Path(output).resolve()
    if output.exists():
        if not resume:
            raise ConflictError("Output exists; use a new directory or explicit resume")
        from rsi_lab.engine.continuation import read_record
        manifest = read_record(output / "manifest.json")
        expected = {**settings, "mode": config["mode"]} if profile == "banking-frozen" else settings
        if manifest["config"] != expected or manifest.get("mode", config["mode"]) != config["mode"]:
            raise ConflictError("Cannot resume with different settings")
    else:
        runner.prepare(output, mode=config["mode"], config=settings)
    return runner.run(output)


def inspect_run(output):
    from rsi_lab.engine.continuation import read_record

    protocol = read_record(Path(output) / "manifest.json")["protocol"]
    for profile in PROFILES:
        config = default_config(profile)
        expected = config.get("protocol", config.get("settings", {}).get("protocol"))
        if protocol == expected:
            return _runner(profile).inspect(Path(output))
    raise ValidationError("Use review-frozen for a run made with a different frozen protocol")

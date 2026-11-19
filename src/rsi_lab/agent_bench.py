"""Public configuration and execution API. Default runs make zero API calls."""
from copy import deepcopy
import json
from pathlib import Path

from rsi_lab.errors import ConflictError, ValidationError
from rsi_lab.methods import check_available

PROFILES = ("matrix", "banking-frozen", "banking-h2", "safety-study", "seabench-controller", "disclosure-audit", "scoring-calibration")
PLANNED = ("safety-study", "seabench-controller", "disclosure-audit", "scoring-calibration")


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
    if profile in PLANNED:
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
               "safety-study": "safety_study", "seabench-controller": "seabench_study", "disclosure-audit": "disclosure_audit",
               "scoring-calibration": "scoring_study"}
    if profile not in modules:
        raise ValidationError(f"Unknown profile {profile!r}; choose {', '.join(PROFILES)}")
    return import_module("rsi_lab.studies." + modules[profile])


def plan_experiment(config):
    """Resolve a selected study allocation without creating providers or dispatching calls."""
    if not isinstance(config, dict) or config.get("profile") not in PLANNED:
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
    if expected_plan is not None and profile not in PLANNED:
        raise ValidationError("Expected plans apply to planned study allocations")
    if profile == "matrix" or profile in PLANNED:
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
        from rsi_lab.infra.records import read_record
        manifest = read_record(output / "manifest.json")
        expected = {**settings, "mode": config["mode"]} if profile == "banking-frozen" else settings
        if manifest["config"] != expected or manifest.get("mode", config["mode"]) != config["mode"]:
            raise ConflictError("Cannot resume with different settings")
    else:
        runner.prepare(output, mode=config["mode"], config=settings)
    return runner.run(output)


def _harness_binding(value):
    """Read resources once; subsequent planning and resume use saved contents."""
    from rsi_lab.harness import Harness, loads
    if isinstance(value, (str, Path)):
        value = Harness.from_directory(value)
    if isinstance(value, Harness):
        return {"source": value.dumps()}
    if type(value) is dict and set(value) == {"source"}:
        return {"source": loads(value["source"]).dumps()}
    raise ValidationError("Harness must be a resource directory, Harness, or a source binding")


def _evaluation_config(method, *, experiment=None, config=None, review=None, harness=None):
    from rsi_lab.methods import method as lookup
    lookup(method)
    settings = (load_config(config) if isinstance(config, (str, Path)) else deepcopy(config))
    if experiment is not None or settings is None:
        from rsi_lab.experiments import experiment_config
        settings = experiment_config(experiment if experiment is not None else "local-control-v1", settings)
    if not isinstance(settings, dict):
        raise ValidationError("Configuration must be a JSON object")
    if settings.get("profile") not in ("matrix", "safety-study", "seabench-controller"):
        raise ValidationError("evaluate requires a method-comparison profile")
    if harness is not None:
        binding = _harness_binding(harness)
        if "harness" in settings and _harness_binding(settings["harness"]) != binding:
            raise ValidationError("Harness argument differs from the configured Harness")
        settings["harness"] = binding
    elif "harness" in settings:
        settings["harness"] = _harness_binding(settings["harness"])
    settings["methods"] = list(dict.fromkeys(["frozen", method]))
    if method != "hyperagents":
        settings.pop("hyperagents_meta_modes", None)
    if review is not None:
        if experiment is not None:
            raise ValidationError("Named experiments fix review semantics; use a full configuration for custom review")
        if settings["profile"] != "seabench-controller":
            raise ValidationError("Independent review requires a seabench-controller configuration")
        settings["review"] = deepcopy(review)
        settings["arms"] = ["native_only", "behavior_review"]
    if settings["profile"] == "seabench-controller" and not any(k in settings for k in ("calibration", "frozen_evaluation")):
        from rsi_lab.studies.risk_report import validate_spec
        settings.setdefault("risk_report", validate_spec(None))
    check_available(settings["methods"])
    return settings


def preflight(method, *, experiment=None, config=None, review=None, harness=None):
    """Validate declarations and allocation, not native fidelity or judge accuracy."""
    from rsi_lab.methods import method_capabilities, plugin_bindings
    from rsi_lab.serialization import digest
    settings = _evaluation_config(method, experiment=experiment, config=config, review=review, harness=harness)
    if settings["profile"] in PLANNED:
        plan = plan_experiment(settings)
    else:
        runner = _runner(settings["profile"])
        settings = runner._validate(settings)
        roots = runner._matrix(settings)
        plan = {"protocol": settings["protocol"], "root_count": len(roots),
                "roots": roots, "method_plugins": plugin_bindings(settings["methods"])}
    return {"protocol": "rsi-preflight-v1", "method": method,
            "config": settings, "config_sha256": digest(settings),
            "plan": plan, "plan_sha256": digest(plan),
            "capabilities": plan.get("method_capabilities") or
                            {name: method_capabilities(name) for name in settings["methods"]},
            "checks": {"declarations_and_allocation": "passed", "interface_execution": "not_run",
                       "mechanism_controls": "not_run", "natural_calibration": "not_run"},
            "platform_api_calls": 0}


class EvaluationResult(dict):
    """The existing summary mapping, with paths for locating an automatic run."""

    def __init__(self, summary, output):
        super().__init__(summary)
        self.output = Path(output).resolve()
        self.report_path = self.output / "report.md"


def evaluate(method, output=None, *, experiment=None, config=None, review=None,
             harness=None, resume=False):
    """Run a registered method with a matched frozen reference.

    Named experiments accept restricted runtime overrides. Without an experiment,
    ``config`` retains the full-configuration API; without either, use the zero-API
    local control. Completed resume without overrides reads the saved configuration.
    """
    if resume:
        if output is None:
            raise ValidationError("Resume requires the original output directory")
        if config is None and review is None:
            from rsi_lab.infra.records import read_record
            from rsi_lab.methods import method as lookup
            lookup(method)
            settings = read_record(Path(output) / "manifest.json")["config"]
            if settings["methods"] != list(dict.fromkeys(["frozen", method])):
                raise ConflictError("Saved run belongs to a different method comparison")
            if experiment is not None and settings.get("experiment", {}).get("id") != experiment:
                raise ConflictError("Saved run belongs to a different experiment")
            if harness is not None and settings.get("harness") != _harness_binding(harness):
                raise ConflictError("Saved run belongs to a different Harness")
        else:
            settings = _evaluation_config(method, experiment=experiment, config=config, review=review, harness=harness)
        return EvaluationResult(run_experiment(settings, output, resume=True), output)
    checked = preflight(method, experiment=experiment, config=config, review=review, harness=harness)
    settings = checked["config"]
    if output is None:
        from uuid import uuid4
        label = settings.get("experiment", {}).get("id", settings["profile"])
        output = Path("runs") / f"{method}-{label}-{uuid4().hex[:12]}"
    plan = checked["plan"] if settings["profile"] in PLANNED else None
    return EvaluationResult(run_experiment(settings, output, expected_plan=plan), output)


def inspect_run(output):
    from rsi_lab.infra.records import read_record

    protocol = read_record(Path(output) / "manifest.json")["protocol"]
    for profile in PROFILES:
        config = default_config(profile)
        expected = config.get("protocol", config.get("settings", {}).get("protocol"))
        if protocol == expected:
            return _runner(profile).inspect(Path(output))
    raise ValidationError("Use review-frozen for a run made with a different frozen protocol")

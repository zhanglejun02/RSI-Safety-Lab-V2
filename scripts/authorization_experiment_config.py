"""Freeze the authorization Bash settings through the public planning API.

Planning, source verification and status make zero model calls. Execution forwards
to the public ``rsi-lab run`` command; no alternate runner or retries live here.
"""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
from urllib.parse import urlsplit


FIELDS = {"methods", "arms", "seeds", "slots", "training", "review", "budget",
          "models", "statistics", "execution"}
OPTIONAL = {"evaluation", "prompts", "public_rollout_cache", "meta_ablation", "pause_on_unknown", "rating"}
FROZEN_FILES = ("settings.json", "config.json", "plan.json", "launch.sh",
                "config-builder.py", "source-helper.py", "execution-source.json")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def _source_helper(path):
    spec = importlib.util.spec_from_file_location("authorization_source_helper", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resolve_settings(settings, actor="deepseek", strategy="baseline"):
    """Apply Bash-declared actor and strategy presets before freezing a new run."""
    if type(settings) is not dict:
        raise ValueError("Launcher settings must be an object")
    resolved = deepcopy(settings)
    presets = resolved.pop("actor_presets", None)
    if presets is None:
        if actor != "deepseek":
            raise ValueError("Actor preset is not declared: " + actor)
    else:
        if type(presets) is not dict or actor not in presets or type(presets[actor]) is not dict:
            raise ValueError("Actor preset is not declared: " + actor)
        resolved["models"]["actor"].update(presets[actor])
    strategies = resolved.pop("strategy_presets", None)
    if strategy not in ("baseline", "structured"):
        raise ValueError("Unknown screening strategy")
    if strategies is None:
        if strategy != "baseline":
            raise ValueError("Structured strategy is not declared")
    else:
        if (type(strategies) is not dict or set(strategies) != {"baseline", "structured"}
                or strategies["baseline"] != "" or type(strategies["structured"]) is not str
                or not strategies["structured"].strip()):
            raise ValueError("Declare an unchanged baseline and a nonempty structured suffix")
        if strategy == "structured":
            from rsi_lab.agents.runtime import DEFAULT_INSTRUCTIONS
            prompts = resolved.setdefault("prompts", {})
            if "initial_instructions" in prompts:
                raise ValueError("Structured strategy appends to the common founder; omit an initial prompt override")
            prompts["initial_instructions"] = DEFAULT_INSTRUCTIONS + "\n\n" + strategies[strategy]
    for model in resolved["models"].values():
        if (model and model.get("model") == "kimi-k2.6"
                and urlsplit(model.get("base_url", "")).hostname in {"api.moonshot.cn", "api.moonshot.ai"}):
            mode = model.get("thinking_mode")
            if mode not in ("disabled", "enabled") or model.get("temperature") != (1.0 if mode == "enabled" else 0.6):
                raise ValueError("Use the validated Kimi recipe: disabled/0.6 or enabled/1.0")
    return resolved


def build(settings, *, mode="http", screen=False, actor="deepseek", strategy="baseline"):
    if isinstance(settings, dict) and settings.get("profile") == "update-confirmation":
        from rsi_lab.studies.update_confirmation import resolve_study
        if screen or actor != "deepseek" or strategy != "baseline":
            raise ValueError("Update confirmation uses its declared frozen-source profile")
        return resolve_study(settings, mode=mode)
    if isinstance(settings, dict) and settings.get("profile") == "update-search":
        from rsi_lab.studies.update_search import validate_config
        if screen or actor != "deepseek" or strategy != "baseline":
            raise ValueError("Update search uses its declared fixed profile, not screening overrides")
        config = {**deepcopy(settings), "mode": mode}
        if mode == "scripted":
            config["models"] = {"actor": None, "editor": None, "judge": None}
        return validate_config(config)
    from rsi_lab.studies.authorization_study import default_config, validate_config

    settings = resolve_settings(settings, actor, strategy)
    if type(settings) is not dict or set(settings) - OPTIONAL != FIELDS:
        raise ValueError("Use the complete authorization launcher parameter block")
    if mode not in ("scripted", "http"):
        raise ValueError("Mode must be scripted or http")
    config = default_config()
    config.update(deepcopy(settings))
    config["mode"] = mode
    if mode == "scripted":
        config["models"] = {"actor": None, "editor": None, "judge": None}
    elif config["models"].get("judge") is not None:
        raise ValueError("Authorization outcomes use the deterministic environment, not an LLM judge")
    if screen:
        config.update(methods=["frozen"], arms=["native_only"])
    return validate_config(config)


def prepare(directory, settings, *, mode, screen, launcher, actor="deepseek", strategy="baseline", runtime=None):
    config = build(settings, mode=mode, screen=screen, actor=actor, strategy=strategy)
    packaged = ({**settings, "selected_actor": actor, "selected_strategy": strategy}
                if "actor_presets" in settings else settings)
    return freeze_config(directory, packaged, config, mode=mode, screen=screen, launcher=launcher, runtime=runtime)


def freeze_config(directory, settings, config, *, mode, screen, launcher, runtime=None):
    """Shared immutable campaign packaging for an already resolved public profile."""
    from rsi_lab.agent_bench import plan_experiment
    from rsi_lab.infra.records import save_record

    plan = plan_experiment(config)
    directory = Path(directory).resolve()
    directory.parent.mkdir(parents=True, exist_ok=True)
    directory.mkdir()  # Never overwrite a prior plan, even if it has not run.
    write(directory / "settings.json", settings)
    write(directory / "config.json", config)
    save_record(directory / "plan.json", plan)
    shutil.copyfile(launcher, directory / "launch.sh")
    shutil.copyfile(__file__, directory / "config-builder.py")
    shutil.copyfile(Path(__file__).with_name("background_experiment.py"), directory / "source-helper.py")
    frozen_files = list(FROZEN_FILES)
    if runtime is not None:
        shutil.copyfile(runtime, directory / "screen-runtime.sh")
        frozen_files.append("screen-runtime.sh")
    _source_helper(directory / "source-helper.py").freeze_source(directory)
    write(directory / "campaign.json", {
        "protocol": "authorization-campaign-v1", "mode": mode, "screen": screen,
        "confirmatory": plan.get("confirmatory", False), "automatic_retry": False,
        "files": {name: sha(directory / name) for name in frozen_files},
    })
    return {"campaign": str(directory), "mode": mode, "screen": screen,
            "roots": len(plan["roots"]), "slots": config.get("slots", 0),
            "implementation": plan["implementation"], "api_calls": 0}


def verify(directory):
    directory = Path(directory).resolve()
    binding = read(directory / "campaign.json")
    if (binding.get("protocol") != "authorization-campaign-v1"
            or set(binding.get("files", {})) not in (set(FROZEN_FILES), set(FROZEN_FILES) | {"screen-runtime.sh"})):
        raise ValueError("Invalid authorization campaign binding")
    for name, expected in binding["files"].items():
        path = directory / name
        if path.is_symlink() or not path.is_file() or sha(path) != expected:
            raise ValueError("Frozen campaign input changed: " + name)
    _source_helper(directory / "source-helper.py").verify_source(directory)
    config = read(directory / "config.json")
    if config["mode"] != binding["mode"]:
        raise ValueError("Campaign mode differs from its frozen binding")
    return config


def status(directory):
    from rsi_lab.infra.records import read_record

    directory = Path(directory).resolve()
    config = verify(directory)
    plan = read_record(directory / "plan.json")
    run = directory / "run"
    root_dirs = [run / root["path"] for root in plan["roots"]]
    result = {"campaign": str(directory), "mode": config["mode"],
            "status": ("completed" if (run / "summary.json").exists() else
                       "started_incomplete" if run.exists() else "prepared"),
            "roots": len(root_dirs),
            "generated_roots": sum((p / "root.json").exists() or (p / "generation.json").exists() for p in root_dirs),
            "evaluated_roots": sum((p / "scores.json").exists() for p in root_dirs),
            "process_liveness_assessed": False, "api_calls": 0}
    if config["profile"] == "update-confirmation":
        result.update(generated_roots=None, roots_kind="measurement_blocks_not_search_roots",
                      reviewed_blocks=sum((p / "reviews.json").exists() for p in root_dirs))
    return result


def load_credentials(directory, env_file):
    """Accept the existing shared provider file without weakening its parser.

    Both declared provider keys may share one private file. Loading a variable
    does not create a provider or dispatch a call. Unknown assignments still fail.
    Completed resume never reads a credential file.
    """
    directory = Path(directory)
    config = read(directory / "config.json")
    if config["mode"] != "http" or (directory / "run/summary.json").is_file():
        return
    from rsi_lab.cli import _credential_names
    from rsi_lab.infra.environment import load_environment
    allowed = _credential_names(config) | {"DEEPSEEK_API_KEY", "MOONSHOT_API_KEY", "SSL_CERT_FILE"}
    load_environment(env_file, tuple(allowed))


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--mode", choices=("scripted", "http"), default="http")
    parser.add_argument("--screen", action="store_true")
    parser.add_argument("--launcher", type=Path)
    parser.add_argument("--runtime", type=Path)
    parser.add_argument("--actor", choices=("deepseek", "kimi"), default="deepseek")
    parser.add_argument("--strategy", choices=("baseline", "structured"), default="baseline")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--cli-args", nargs=argparse.REMAINDER, default=[])
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--verify", action="store_true")
    action.add_argument("--status", action="store_true")
    action.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.execute:
        if args.env_file is None or not args.cli_args:
            parser.error("--execute requires --env-file and --cli-args")
        verify(args.directory)
        load_credentials(args.directory, args.env_file)
        from rsi_lab.cli import main as public_cli
        raise SystemExit(public_cli(["run", *args.cli_args]))
    elif args.status:
        result = status(args.directory)
    elif args.verify:
        config = verify(args.directory)
        result = {"verified": True, "mode": config["mode"], "api_calls": 0}
    else:
        if args.launcher is None:
            parser.error("--launcher is required when preparing a campaign")
        result = prepare(args.directory, json.load(sys.stdin), mode=args.mode,
                         screen=args.screen, launcher=args.launcher, actor=args.actor,
                         strategy=args.strategy, runtime=args.runtime)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as exc:
        print(f"ConfigurationError: {exc}", file=sys.stderr)
        raise SystemExit(2) from None

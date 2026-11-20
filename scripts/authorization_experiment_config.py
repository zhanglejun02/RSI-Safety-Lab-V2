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


FIELDS = {"methods", "arms", "seeds", "slots", "training", "review", "budget",
          "models", "statistics", "execution"}
OPTIONAL = {"evaluation"}
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


def build(settings, *, mode="http", screen=False):
    from rsi_lab.studies.authorization_study import default_config, validate_config

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


def prepare(directory, settings, *, mode, screen, launcher):
    config = build(settings, mode=mode, screen=screen)
    return freeze_config(directory, settings, config, mode=mode, screen=screen, launcher=launcher)


def freeze_config(directory, settings, config, *, mode, screen, launcher):
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
    _source_helper(directory / "source-helper.py").freeze_source(directory)
    write(directory / "campaign.json", {
        "protocol": "authorization-campaign-v1", "mode": mode, "screen": screen,
        "confirmatory": False, "automatic_retry": False,
        "files": {name: sha(directory / name) for name in FROZEN_FILES},
    })
    return {"campaign": str(directory), "mode": mode, "screen": screen,
            "roots": len(plan["roots"]), "slots": config["slots"],
            "implementation": plan["implementation"], "api_calls": 0}


def verify(directory):
    directory = Path(directory).resolve()
    binding = read(directory / "campaign.json")
    if (binding.get("protocol") != "authorization-campaign-v1"
            or set(binding.get("files", {})) != set(FROZEN_FILES)):
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
    return {"campaign": str(directory), "mode": config["mode"],
            "status": ("completed" if (run / "summary.json").exists() else
                       "started_incomplete" if run.exists() else "prepared"),
            "roots": len(root_dirs),
            "generated_roots": sum((p / "root.json").exists() or (p / "generation.json").exists() for p in root_dirs),
            "evaluated_roots": sum((p / "scores.json").exists() for p in root_dirs),
            "process_liveness_assessed": False, "api_calls": 0}


def load_credentials(directory, env_file):
    """Accept the existing shared provider file without weakening its parser.

    Kimi is an authorized, unused provider in this task. Loading its variable
    does not create a judge or dispatch a call. Unknown assignments still fail.
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
                         screen=args.screen, launcher=args.launcher)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as exc:
        print(f"ConfigurationError: {exc}", file=sys.stderr)
        raise SystemExit(2) from None

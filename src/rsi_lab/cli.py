"""Single CLI for method selection, frozen profiles, runs and inspection."""
import argparse
import json
from pathlib import Path
import sys

from rsi_lab.agent_bench import PROFILES, default_config, inspect_run, run_experiment
from rsi_lab.errors import LabError, ValidationError
from rsi_lab.methods import METHODS, describe_methods


def parser():
    cli = argparse.ArgumentParser(prog="rsi-lab", description=__doc__)
    commands = cli.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="List method scopes, platforms and benchmark profiles")
    config = commands.add_parser("config", help="Print an editable, zero API configuration")
    config.add_argument("--profile", choices=PROFILES, default="matrix")
    config.add_argument("--methods", nargs="+", choices=METHODS)
    run = commands.add_parser("run", help="Run or explicitly resume a frozen allocation")
    selection = run.add_mutually_exclusive_group()
    selection.add_argument("--config", type=Path)
    selection.add_argument("--profile", choices=PROFILES, default="matrix")
    run.add_argument("--methods", nargs="+", choices=METHODS)
    run.add_argument("--output", required=True, type=Path)
    run.add_argument("--resume", action="store_true")
    run.add_argument("--env-file", type=Path)
    inspect = commands.add_parser("inspect", help="Verify a completed run without model calls")
    inspect.add_argument("--output", required=True, type=Path)
    review = commands.add_parser("review-frozen", help="Inspect an archived source/run in an isolated copy")
    review.add_argument("--run", required=True, type=Path)
    review.add_argument("--output", required=True, type=Path)
    return cli


def select_methods(config, names):
    if not names:
        return config
    if config["profile"] == "matrix":
        config["methods"] = names
    elif config["profile"] == "banking-h2":
        config["settings"]["methods"] = names
    elif names != ["frozen"]:
        raise ValidationError("The frozen profile supports only the frozen method")
    return config


def _credential_names(config):
    """Read names, never values, from explicit HTTP model configuration."""
    if isinstance(config, dict):
        result = {config["api_key_env"]} if isinstance(config.get("api_key_env"), str) else set()
        for value in config.values():
            result.update(_credential_names(value))
        return result
    return set()


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "list":
            from rsi_lab.benchmarks import BENCHMARKS
            result = {"methods": describe_methods(), "benchmarks": list(BENCHMARKS), "profiles": PROFILES,
                      "scope": "AgentDojo is the external benchmark; local_transfer is a synthetic CONTROL fixture"}
        elif args.command == "config":
            result = select_methods(default_config(args.profile), args.methods)
        elif args.command == "run":
            config = json.loads(args.config.read_text()) if args.config else default_config(args.profile)
            config = select_methods(config, args.methods)
            if args.env_file:
                from rsi_lab.infra.environment import load_environment
                load_environment(args.env_file, tuple(_credential_names(config) | {"SSL_CERT_FILE"}))
            summary = run_experiment(config, args.output, resume=args.resume)
            result = {"output": str(args.output.resolve()), "protocol": summary["protocol"],
                      "origin": summary.get("origin", summary.get("mode", config["mode"])),
                      "report": str(args.output.resolve() / "report.md")}
        elif args.command == "inspect":
            summary = inspect_run(args.output)
            result = {"protocol": summary["protocol"], "verified": True, "api_calls": 0}
        else:
            from rsi_lab.review import review
            result = review(args.run, args.output)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (LabError, ValueError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

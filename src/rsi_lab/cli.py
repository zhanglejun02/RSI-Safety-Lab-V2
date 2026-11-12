"""Single CLI for method selection, frozen profiles, runs and inspection."""
import argparse
import json
from pathlib import Path
import sys

from rsi_lab.agent_bench import PROFILES, default_config, inspect_run, load_config, plan_experiment, run_experiment
from rsi_lab.errors import LabError, ValidationError
from rsi_lab.methods import METHODS, describe_methods


def parser():
    cli = argparse.ArgumentParser(prog="rsi-lab", description=__doc__)
    commands = cli.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="List method scopes, platforms and benchmark profiles")
    catalog = commands.add_parser("catalog", help="List native benchmark tasks without running episodes")
    catalog.add_argument("--benchmark", choices=("agentdojo", "seabench"), default="agentdojo")
    catalog.add_argument("--source", type=Path, default=Path("runs/vendor/SEABench"), help="Pinned SEABench checkout")
    plan = commands.add_parser("plan", help="Resolve and freeze the selected evaluation allocation; zero API calls")
    plan.add_argument("--config", required=True, type=Path)
    plan.add_argument("--output", type=Path, help="Optional immutable plan file for run --plan")
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
    run.add_argument("--plan", type=Path, help="Require this frozen allocation and source identity")
    for command in (plan, run):
        command.add_argument("--execution", type=Path, help="Replace execution settings from this JSON object; requires --config")
    inspect = commands.add_parser("inspect", help="Verify a completed run without model calls")
    inspect.add_argument("--output", required=True, type=Path)
    review = commands.add_parser("review-frozen", help="Inspect an archived source/run in an isolated copy")
    review.add_argument("--run", required=True, type=Path)
    review.add_argument("--output", required=True, type=Path)
    batch = commands.add_parser("batch", help="Run a fixed list of planned jobs; stop on failure, never restart calls")
    batch.add_argument("--jobs", required=True, type=Path)
    batch.add_argument("--output", required=True, type=Path)
    batch.add_argument("--env-file", type=Path)
    batch.add_argument("--resume", action="store_true")
    return cli


def select_methods(config, names):
    if not names:
        return config
    if config["profile"] in ("matrix", "safety-study", "seabench-controller"):
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
            from rsi_lab.benchmarks import describe_benchmarks
            descriptions = describe_benchmarks()
            result = {"methods": describe_methods(), "benchmarks": [b["name"] for b in descriptions],
                      "benchmark_capabilities": descriptions, "profiles": PROFILES,
                      "scope": "Separate injection security, agent harmfulness and text refusal metrics; scripted results are CONTROL"}
        elif args.command == "catalog":
            if args.benchmark == "seabench":
                from rsi_lab.benchmarks.seabench import catalog
                result = catalog(args.source)
            else:
                from rsi_lab.benchmarks.agentdojo_suite import available_catalog
                result = available_catalog()
        elif args.command == "plan":
            result = plan_experiment(load_config(args.config, execution=args.execution))
            if args.output:
                from rsi_lab.engine.continuation import save_record
                if args.output.exists():
                    raise ValidationError("Plan output exists; choose a new path")
                save_record(args.output, result)
        elif args.command == "config":
            result = select_methods(default_config(args.profile), args.methods)
        elif args.command == "run":
            if args.execution and not args.config:
                raise ValidationError("--execution requires --config")
            config = load_config(args.config, execution=args.execution) if args.config else default_config(args.profile)
            config = select_methods(config, args.methods)
            if args.env_file:
                from rsi_lab.infra.environment import load_environment
                load_environment(args.env_file, tuple(_credential_names(config) | {"SSL_CERT_FILE"}))
            from rsi_lab.engine.continuation import read_record
            expected = read_record(args.plan) if args.plan else None
            summary = run_experiment(config, args.output, resume=args.resume, expected_plan=expected)
            result = {"output": str(args.output.resolve()), "protocol": summary["protocol"],
                      "origin": summary.get("origin", summary.get("mode", config["mode"])),
                      "report": str(args.output.resolve() / "report.md")}
        elif args.command == "batch":
            from rsi_lab.infra.batch import run
            result = run(args.jobs, args.output, resume=args.resume, env_file=args.env_file)
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

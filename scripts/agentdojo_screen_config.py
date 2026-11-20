"""Prepare the fixed AgentDojo development screen; never dispatch model calls."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys


def campaign_helper():
    path = Path(__file__).with_name("authorization_experiment_config.py")
    spec = importlib.util.spec_from_file_location("screen_campaign", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build(settings, *, mode="http"):
    from rsi_lab.studies.safety_study import default_config, validate_config

    config = default_config()
    allowed = {"methods", "arms", "seeds", "slots", "training", "gate", "budget", "models",
               "evaluation", "statistics", "execution", "study"}
    if type(settings) is not dict or set(settings) != allowed:
        raise ValueError("Use the complete AgentDojo screen parameter block")
    config.update(deepcopy(settings))
    if config["methods"] != ["frozen"] or config["arms"] != ["native_only"]:
        raise ValueError("This screening launcher does not start RSI or review comparisons")
    if mode not in ("http", "scripted"):
        raise ValueError("Invalid screen mode")
    config["mode"] = mode
    if mode == "scripted":
        config["models"] = {"actor": None, "editor": None, "judge": None}
    if config["models"]["judge"] is not None or config["evaluation"] != {"xstest_ids": [], "agentharm": None}:
        raise ValueError("This screen uses only AgentDojo state/trace graders, no LLM judge")
    return validate_config(config)


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--mode", choices=("http", "scripted"), default="http")
    parser.add_argument("--launcher", required=True, type=Path)
    args = parser.parse_args()
    settings = json.load(sys.stdin)
    config = build(settings, mode=args.mode)
    # The fully resolved config and this exact builder's bytes are retained.
    packaged = {**settings, "builder_source": Path(__file__).read_text()}
    result = campaign_helper().freeze_config(args.directory, packaged, config,
        mode=args.mode, screen=True, launcher=args.launcher)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as exc:
        print(f"ConfigurationError: {exc}", file=sys.stderr)
        raise SystemExit(2) from None

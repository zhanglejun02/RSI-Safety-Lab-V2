"""Zero API release acceptance: native matrix and byte-identical completed resume."""
import argparse
import json
from pathlib import Path
import platform

from rsi_lab.agent_bench import default_config, run_experiment
from rsi_lab.engine.continuation import read_record
from rsi_lab.methods import METHODS
from rsi_lab.review import inventory


def validate(output):
    config = default_config()
    config["methods"] = [name for name, spec in METHODS.items() if platform.system() in spec.platforms]
    summary = run_experiment(config, output)
    before = inventory(output)
    assert run_experiment(config, output, resume=True) == summary
    assert before == inventory(output)
    rows = summary["rows"]
    slots = [slot for row in rows for slot in row["slots"]]
    effects = [read_record(path) for path in output.glob("roots/*/episodes/*/result.json")]
    assert summary["paid_calls"] == 0 and summary["origin"] == "control"
    result = {"protocol": summary["protocol"], "origin": "CONTROL", "api_calls": 0,
              "methods": config["methods"], "roots": len(rows), "slots": len(slots),
              "episodes": len(effects), "actor_calls": sum(r["actor_usage"]["dispatched_calls"] for r in rows),
              "editor_calls": sum(r["editor_usage"]["dispatched_calls"] for r in rows if r["editor_usage"]),
              "tool_calls": sum(r["metrics"]["tool_calls"] for r in effects),
              "native_admitted": sum(s["native_admitted"] is True for s in slots),
              "committed": sum(s["platform_committed"] for s in slots),
              "active_changes": sum(s["active_source_changed"] for s in slots),
              "archive_only": sum(s["platform_committed"] and not s["active_source_changed"] for s in slots),
              "resume_unchanged_files": len(before)}
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(validate(args.output.resolve()), indent=2))

"""Read-only verification/export for a completed fixed-update confirmation.

Replays saved simulated tool actions, never the model. Writes only a new output
directory and retains the predeclared statistics from the frozen run.
"""
import argparse
from collections import Counter
import json
from pathlib import Path

from rsi_lab.benchmarks import effect_catalog
from rsi_lab.infra.records import read_record
from rsi_lab.review import inventory
from rsi_lab.serialization import digest
from rsi_lab.studies.update_confirmation import PROTOCOL, inspect
from summarize_agentdojo_rsi import measured_metrics, verify_saved_effects


def verify_row(directory, row, catalog):
    path = (directory / row["record_path"]).resolve()
    if not path.is_relative_to(directory.resolve()):
        raise ValueError("Recorded execution escapes its measurement block")
    saved = read_record(path)
    if (saved["binding"]["source_sha256"] != row["source_sha256"]
            or saved["binding"]["case_sha256"] != row["case_sha256"]):
        raise ValueError("Measurement row and execution identity differ")
    record = saved["record"]
    matched = verify_saved_effects(record, catalog)
    if matched:
        verdict, metrics = record["verdict"], record["metrics"]
        risk = not metrics["security"] if (metrics.get("complete") or metrics["security"] is False) else None
        if row["task_success"] != verdict["task_success"] or row["violation"] != risk:
            raise ValueError("Summary labels differ from saved execution")
    return record, matched


def collect(run):
    run = Path(run).resolve()
    before = inventory(run)
    summary = inspect(run)
    if summary["protocol"] != PROTOCOL:
        raise ValueError("Requires a completed saved-update confirmation")
    manifest = read_record(run / "manifest.json")
    catalog = effect_catalog(manifest["config"]["training"])
    replay, execution, positives, per_task = Counter(), [], [], []
    for block in summary["rows"]:
        directory = run / block["path"]
        for phase, measurements in (("public", block["public_assessments"]),
                                    ("independent", block["assessments"])):
            for variant, rows in measurements.items():
                joint, stops, exposure, calls = Counter(), Counter(), [], Counter()
                for row in rows:
                    record, matched = verify_row(directory, row, catalog)
                    replay[phase + ("_matched" if matched else "_unavailable")] += 1
                    outcome = ("missing" if type(row["task_success"]) is not bool or type(row["violation"]) is not bool
                               else ("complete" if row["task_success"] else "incomplete") +
                               ("_unsafe" if row["violation"] else "_safe"))
                    joint[outcome] += 1
                    stops[record.get("stop_reason", record.get("error", "unknown"))] += 1
                    for key in ("actor_calls", "tool_calls"):
                        if type(record["metrics"].get(key)) is int:
                            calls[key] += record["metrics"][key]
                    verdict = record["verdict"]
                    if row["attack_present"] and type(verdict.get("injection_observed")) is bool:
                        exposure.append(verdict["injection_observed"])
                    if row["violation"] is True:
                        positives.append({"block": block["block"], "phase": phase, "variant": variant,
                            "source_sha256": row["source_sha256"], "case_id": row["case_id"],
                            "cohort": row["cohort"], "task_success": row["task_success"],
                            "record": str(Path(block["path"]) / row["record_path"]),
                            "final_state_sha256": verdict["final_state_sha256"], "effects": verdict["effects"]})
                execution.append({"block": block["block"], "phase": phase, "variant": variant,
                    "joint_outcomes": dict(joint), "stops": dict(stops), **calls,
                    "attack_exposure_known": len(exposure), "attack_exposed": sum(exposure)})
    for name in manifest["config"]["variants"]:
        rows = [r for block in summary["rows"] for r in block["assessments"][name]]
        for task in sorted({r["pair_id"] for r in rows}):
            selected = [r for r in rows if r["pair_id"] == task]
            per_task.append({"variant": name, "task": task, "cohort": selected[0]["cohort"],
                "metrics": measured_metrics(selected),
                "attacked": measured_metrics([r for r in selected if r["attack_present"]]),
                "clean": measured_metrics([r for r in selected if not r["attack_present"]])})
    if inventory(run) != before:
        raise ValueError("Read-only verification changed completed artifacts")
    return {"run": str(run), "origin": summary["origin"], "implementation": manifest["implementation"],
        "inventory_sha256": digest(before), "file_count": len(before), "effect_replay": dict(replay),
        "resources": summary["resources"], "criteria": summary["criteria"],
        "table": summary["table"], "comparisons": summary["comparisons"],
        "sham_control_warning": summary["sham_control_warning"], "per_task": per_task,
        "execution": execution, "positives": positives, "api_calls_for_analysis": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    run, output = args.run.resolve(), args.output.resolve()
    if output.is_relative_to(run) or output.exists():
        parser.error("Use a new output directory outside the immutable run")
    result = collect(run)
    output.mkdir(parents=True)
    (output / "verified-metrics.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    for name in ("report.md", "metrics.csv"):
        (output / name).write_bytes((run / name).read_bytes())
    print(json.dumps({"output": str(output), "effect_replay": result["effect_replay"],
                      "api_calls": 0, "inventory_sha256": result["inventory_sha256"]}, indent=2))


if __name__ == "__main__":
    main()

"""Read-only tables for the small improvement-safety development pilot."""
import argparse
import json
from pathlib import Path
from statistics import mean

from rsi_lab.api import SystemSnapshot
from rsi_lab.infra.records import read_record
from rsi_lab.review import inventory
from rsi_lab.serialization import digest
from rsi_lab.studies.authorization_study import inspect


def collect(directory):
    before = inventory(directory)
    summary = inspect(directory)
    result = {"run": str(directory), "origin": summary["origin"], "sources": [], "roots": []}
    for row in summary["rows"]:
        saved = read_record(directory / "roots" / row["root_id"] / "root.json")
        founder = digest(SystemSnapshot.from_dict(saved["origin"]).version.component("policy")["source"])
        edited = [s["step"] for s in saved["slots"] if s["mechanism"].get("edited_meta_used")]
        result["roots"].append({"root_id": row["root_id"], "method": row["method"],
            "opportunities": row["opportunities"], "commits": row["commits"],
            "deployment_changes": row["deployment_changes"], "generation_failures": row["generation_failures"],
            "executed_edited_meta_steps": edited,
            "layer_three_eligibility": "available" if edited else "no_executed_edited_meta",
            "resources": row["resources"]})
        for sha, assessment in row["candidate_assessments"].items():
            cases = assessment["cases"]
            completion = [c["authorization"].get("completion") for c in cases]
            completion = [c for c in completion if c is not None]
            result["sources"].append({"root_id": row["root_id"], "method": row["method"], "source": sha,
                "founder": sha == founder, "final": sha == row["final_source_sha256"],
                "metrics": assessment["metrics"],
                "raw_completion": mean(completion) if completion else None,
                "raw_completion_known": len(completion)})
    if inventory(directory) != before:
        raise RuntimeError("Analysis changed the source run")
    result["input_inventory_sha256"] = digest(before)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--meta-run", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    inputs = [p.resolve() for p in (args.run, args.meta_run) if p is not None]
    output = args.output.resolve()
    if any(output == p or p in output.parents for p in inputs):
        parser.error("Analysis output must be outside immutable runs")
    data = [collect(p) for p in inputs]
    lines = ["# Improvement-safety development pilot", "",
             "Two authored templates; repeats and normal/boundary variants are not independent scenarios.",
             "Control runs are wiring evidence. Natural pilot rows are exploratory, not method rankings.", ""]
    fmt = lambda value: "missing" if value is None else f"{100 * value:.2f}%"
    for campaign in data:
        lines += [f"Run: `{campaign['run']}`; origin: **{campaign['origin']}**", "",
                  "| Method | Source | Role | Task successes | Completion | Cost-weighted utility | Violations / known | Missing risk |",
                  "|---|---|---|---:|---:|---:|---:|---:|"]
        for row in campaign["sources"]:
            m = row["metrics"]
            role = ", ".join(k for k in ("founder", "final") if row[k]) or "candidate"
            lines.append(f"| {row['method']} | {row['source'][:12]} | {role} | "
                         f"{m['task_successes']}/{m['task_known']} | {fmt(row['raw_completion'])} | "
                         f"{fmt(m['authorized_completion_rate'])} | {m['violations']}/{m['risk_known']} | {m['risk_missing']} |")
        lines += ["", "| Method | Update opportunities | Commits | Deployment changes | Generation failures | Executed edited-meta steps |",
                  "|---|---:|---:|---:|---:|---|"]
        for row in campaign["roots"]:
            lines.append(f"| {row['method']} | {row['opportunities']} | {row['commits']} | "
                         f"{row['deployment_changes']} | {row['generation_failures']} | {row['executed_edited_meta_steps']} |")
        lines.append("")
    lines += ["Safety is the declared simulated verification/effect predicate, not universal safety.",
              "A matching safe current policy plus an executed altered improver and matched continuation outcomes",
              "are all required before interpreting latent improvement-mechanism risk.",
              "Source reuse within a root is not an independent repeat. Missing labels are not safe zero.", ""]
    output.mkdir(parents=True, exist_ok=True)
    (output / "metrics.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    (output / "report.md").write_text("\n".join(lines))
    print(output / "report.md")


if __name__ == "__main__":
    main()

"""Read-only tables for the small improvement-safety development pilot."""
import argparse
import json
from pathlib import Path
import sqlite3
from statistics import mean

from rsi_lab.agents.runtime import verify
from rsi_lab.api import SystemSnapshot
from rsi_lab.infra.records import read_record
from rsi_lab.review import inventory
from rsi_lab.serialization import digest
from rsi_lab.studies.authorization_study import inspect, _metrics, _sources


def partial_summary(directory):
    """Allocate all frozen cases; absent/unknown observations remain missing.

    This never finalizes or repairs a run. It requires a completed generation
    barrier and binds the read-only projection to its saved roots and manifest.
    """
    manifest = read_record(directory / "manifest.json")
    plan = read_record(directory / "plan.json")
    if digest(plan) != manifest["plan_sha256"]:
        raise ValueError("Saved plan differs from manifest")
    roots = manifest["roots"]
    expected = {r["root_id"]: digest(read_record(directory / r["path"] / "root.json")) for r in roots}
    if read_record(directory / "generation_complete.json") != {"manifest_sha256": digest(manifest), "roots": expected}:
        raise ValueError("Partial analysis needs the frozen generation barrier")
    config, rows = manifest["config"], []
    for root in roots:
        location = directory / root["path"]
        saved = read_record(location / "root.json")
        final, sources, _ = _sources(saved, location, config["evaluation"]["audit_candidates"])
        assessments = {}
        for sha in sources:
            cases = []
            for repeat in range(config["evaluation"]["repeats"]):
                for case in (c for c in plan["catalog"] if c["partition"] == "heldout"):
                    path = location / "independent" / sha / f"{repeat}-{digest(case)}.json"
                    record = read_record(path) if path.exists() else {"metrics": {}, "verdict": {}, "error": "not_attempted"}
                    if "record_sha256" in record:
                        verify(record)
                        if record["case"] != case or digest(record["source"]) != sha:
                            raise ValueError("Independent source/case mismatch")
                    m, v = record["metrics"], record["verdict"]
                    risk = (not m["security"] if type(m.get("security")) is bool
                            and (m.get("complete") or m["security"] is False) else None)
                    cases.append({"case_id": case["case_id"], "repeat": repeat,
                        "utility": m.get("utility"), "task_success": v.get("task_success"),
                        "violation": risk, "protocol_complete": m.get("complete", False),
                        "authorization": v.get("authorization", {}), "error": record.get("error"),
                        "record_path": str(path.relative_to(location))})
            assessments[sha] = {"cases": cases, "metrics": _metrics(cases)}
        resources = dict(saved["search_resources"])
        db = location / "test.sqlite"
        if db.exists():
            with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as connection:
                states = dict(connection.execute("SELECT status,COUNT(*) FROM chat_requests GROUP BY status"))
                totals = connection.execute("SELECT SUM(actual_tokens),SUM(CASE WHEN status IN ('pending','unknown') THEN reserved_tokens ELSE 0 END) FROM chat_requests").fetchone()
            resources["test"] = {"dispatched_calls": sum(states.values()), "request_states": states,
                                 "actual_total_tokens": totals[0] or 0, "reserved_tokens": totals[1] or 0,
                                 "unknown_responses": states.get("unknown", 0)}
        rows.append({"root_id": root["root_id"], "method": root.get("comparison", root["system"]),
            "final_source_sha256": final, "candidate_assessments": assessments,
            "opportunities": len(saved["slots"]), "commits": sum(s["committed"] for s in saved["slots"]),
            "deployment_changes": sum(s["base_source"] != s["active_source"] for s in saved["slots"]),
            "generation_failures": sum(s["error"] is not None for s in saved["slots"]), "resources": resources})
    return {"origin": manifest["origin"], "rows": rows}


def collect(directory):
    before = inventory(directory)
    complete = (directory / "summary.json").exists()
    summary = inspect(directory) if complete else partial_summary(directory)
    result = {"run": str(directory), "origin": summary["origin"], "complete": complete, "sources": [], "roots": []}
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
            actor_calls = []
            for case in cases:
                path = directory / "roots" / row["root_id"] / case["record_path"]
                record = read_record(path) if path.exists() else {"metrics": {}}
                value = record["metrics"].get("actor_calls")
                if value is not None:
                    actor_calls.append(value)
            completion = [c["authorization"].get("completion") for c in cases]
            completion = [c for c in completion if c is not None]
            result["sources"].append({"root_id": row["root_id"], "method": row["method"], "source": sha,
                "founder": sha == founder, "final": sha == row["final_source_sha256"],
                "metrics": assessment["metrics"],
                "raw_completion": mean(completion) if completion else None,
                "raw_completion_known": len(completion),
                "mean_actor_calls": mean(actor_calls) if actor_calls else None,
                "actor_call_observations": len(actor_calls),
                "missing_reasons": {reason: sum(c.get("error") == reason for c in cases)
                                    for reason in sorted({c["error"] for c in cases if c.get("error")})}})
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
        lines += [f"Run: `{campaign['run']}`; origin: **{campaign['origin']}**; completed: **{campaign['complete']}**", "",
                  "| Method | Source | Role | Task successes | Completion | Cost-weighted utility | Mean model calls | Violations / known | Missing risk |",
                  "|---|---|---|---:|---:|---:|---:|---:|---:|"]
        for row in campaign["sources"]:
            m = row["metrics"]
            role = ", ".join(k for k in ("founder", "final") if row[k]) or "candidate"
            lines.append(f"| {row['method']} | {row['source'][:12]} | {role} | "
                         f"{m['task_successes']}/{m['task_known']} | {fmt(row['raw_completion'])} | "
                         f"{fmt(m['authorized_completion_rate'])} | {row['mean_actor_calls']} | "
                         f"{m['violations']}/{m['risk_known']} | {m['risk_missing']} |")
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

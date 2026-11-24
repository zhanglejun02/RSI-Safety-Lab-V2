"""Read-only diagnostics for a completed bounded search; never re-score or call models."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import sqlite3

from rsi_lab.agent_bench import inspect_run
from rsi_lab.infra.records import read_record
from rsi_lab.serialization import digest
from rsi_lab.studies.authorization_study import _metrics
from rsi_lab.studies.update_search_metrics import qualification


def summarize(run):
    saved = inspect_run(run)
    manifest = read_record(run / "manifest.json")
    sources = [rows for root in saved["rows"] for rows in root["assessments"].values()]
    repeats = manifest["config"]["evaluation"]["repeats"]
    prefix = 0
    for repeat in range(repeats):
        groups = [[r for r in rows if r["repeat"] == repeat] for rows in sources]
        if not all(group and all(type(r["utility"]) in (int, float) and type(r["task_success"]) is bool
                                 for r in group) for group in groups):
            break
        prefix += 1
    candidates, parents, roles, scheduling_positives = [], [], {}, []
    for root in saved["rows"]:
        parent = root["assessments"][root["parent_sha256"]]
        prefix_parent = [r for r in parent if r["repeat"] < prefix]
        parents.append({"root_id": root["root_id"], "source_sha256": root["parent_sha256"],
                        "registered": _metrics(parent), "common_prefix": _metrics(prefix_parent)})
        for source_sha, rows in root["assessments"].items():
            for row in rows:
                if row["violation"] is not True:
                    continue
                record = read_record(run / root["path"] / row["record_path"])["record"]
                if "scheduling" not in record["verdict"]:
                    continue
                contacts = record["case"]["data"]["directory"]["contacts"]
                contact_ids = {c["contact_id"] for c in contacts}
                categories = Counter()
                for effect in record["verdict"]["effects"]:
                    if effect.get("authorized") is not False:
                        continue
                    recipient = effect["recipient"]
                    category = ("contact_id_in_recipient_field" if recipient in contact_ids else
                                "other_non_address_identifier" if "@" not in recipient else "address_like_destination")
                    categories[category] += 1
                scheduling_positives.append({"root_id": root["root_id"], "source_sha256": source_sha,
                    "case_id": row["case_id"], "repeat": row["repeat"], "utility": row["utility"],
                    "record_sha256": row["record_sha256"], "destinations": categories})
        for role, resource in root["resources"].items():
            counts = roles.setdefault(role, Counter())
            for key in ("dispatched_calls", "complete_responses", "invalid_responses", "unknown_responses",
                        "actual_total_tokens", "usage_missing_calls", "reserved_tokens"):
                counts[key] += resource[key]
        for proposal in root["proposals"]:
            if "source_sha256" not in proposal:
                continue
            child = root["assessments"][proposal["source_sha256"]]
            prefix_child = [r for r in child if r["repeat"] < prefix]
            q = qualification(parent, child)
            original = next(c for c in saved["candidates"] if c["root_id"] == root["root_id"]
                            and c["attempt"] == proposal["attempt"])
            # The richer classification must not change the frozen measurements.
            assert all(q[key] == value for key, value in original["qualification"].items())
            candidates.append({"root_id": root["root_id"], "strategy": root["strategy"],
                "attempt": proposal["attempt"], "source_sha256": proposal["source_sha256"],
                "policy": proposal["proposal"]["policy"], "registered": _metrics(child),
                "registered_qualification": q, "common_prefix": _metrics(prefix_child),
                "common_prefix_parent": _metrics(prefix_parent),
                "common_prefix_contrast": qualification(prefix_parent, prefix_child) if prefix else None,
                "review": root["reviews"][str(proposal["attempt"])]})
    errors = Counter()
    for database in run.glob("roots/*/*.sqlite"):
        with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as db:
            for status, count in db.execute("""SELECT t.http_status,COUNT(*) FROM chat_requests r
                    LEFT JOIN chat_timings t ON r.request_id=t.request_id
                    WHERE r.status='unknown' GROUP BY t.http_status"""):
                errors["transport_no_http_status" if status is None else "HTTP_" + str(status)] += count
    total = Counter()
    for role in roles.values():
        total.update(role)
    all_final = [r for rows in sources for r in rows]
    return {"protocol": "update-search-diagnostics-v1", "source_run": str(run),
            "source_summary_sha256": digest(saved), "source_manifest_sha256": digest(manifest),
            "registered_repeats": repeats, "common_observed_utility_prefix": prefix,
            "prefix_selection": "post-hoc availability only; not a replacement for the five-repeat endpoint",
            "final_allocation": _metrics(all_final), "final_stop_reasons": dict(Counter(r["stop_reason"] for r in all_final)),
            "distinct_update_sources": len({c["source_sha256"] for c in candidates}),
            "parents": parents, "candidates": candidates, "resources_by_phase": roles,
            "scheduling_positive_destination_audit": scheduling_positives,
            "destination_audit_scope": "descriptive string categories; original labels unchanged; not proof of real delivery",
            "resources_total": total, "unknown_request_errors": errors, "api_calls_for_analysis": 0}


def write_report(output, result):
    output.mkdir(parents=True, exist_ok=True)
    (output / "diagnostics.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    flat, lines = [], ["# Fixed-update search diagnostics", "",
        f"Registered repeats: {result['registered_repeats']}; common observed utility prefix: {result['common_observed_utility_prefix']}.",
        "The table is a post-hoc common-prefix diagnostic. Risk missingness remains explicit; no missing label is safe zero.",
        "Qualification and observed counterexamples still use the original five-repeat rule.", "",
        "| Candidate | Task success (parent → child) ↑ | Parent utility | Child utility | Utility difference | Parent risk ↓ | Child risk ↓ | Child risk missing | Five-repeat criterion | Full / relative review |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|---|"]
    def pct(value):
        return "missing" if value is None else f"{100*value:.2f}%"
    for c in result["candidates"]:
        m, p, q = c["common_prefix"], c["common_prefix_parent"], c["common_prefix_contrast"]
        delta = q["overall"]["utility_delta"] if q else None
        row = {"root_id": c["root_id"], "attempt": c["attempt"], "source_sha256": c["source_sha256"],
               "allocated": m["allocated"], "task_successes": m["task_successes"], "task_known": m["task_known"],
               "task_success_rate": m["task_success_rate"], "parent_task_success_rate": p["task_success_rate"],
               "parent_task_successes": p["task_successes"], "parent_task_known": p["task_known"],
               "utility": m["authorized_completion_rate"], "parent_utility": p["authorized_completion_rate"],
               "utility_difference": delta, "violations": m["violations"], "risk_known": m["risk_known"],
               "risk_missing": m["risk_missing"], "parent_violations": p["violations"], "parent_risk_known": p["risk_known"],
               "criterion_status": c["registered_qualification"]["criterion_status"],
               "full_review": c["review"]["full_validation"]["disposition"],
               "relative_review": c["review"]["behavior_regression"]["disposition"]}
        flat.append(row)
        difference = "missing" if delta is None else f"{100*delta:+.2f} pp"
        lines.append(f"| {c['root_id']} / {c['attempt']} | {pct(p['task_success_rate'])} → {pct(m['task_success_rate'])} | "
                     f"{pct(p['authorized_completion_rate'])} | {pct(m['authorized_completion_rate'])} | {difference} | "
                     f"{p['violations']}/{p['risk_known']} | {m['violations']}/{m['risk_known']} | "
                     f"{m['risk_missing']}/{m['allocated']} | {row['criterion_status']} | {row['full_review']} / {row['relative_review']} |")
    lines += ["", "Utility difference is in percentage points. Task success and harmful effects are distinct endpoints.",
              "The source run is immutable; this export does not replace labels, repeat failed calls, or revise review decisions.",
              "See diagnostics.json for the complete registered allocation, all missing labels, per-repeat counterexamples and call ledgers."]
    (output / "report.md").write_text("\n".join(lines) + "\n")
    with (output / "metrics.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(flat[0]))
        writer.writeheader()
        writer.writerows(flat)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run, output = args.run.resolve(), args.output.resolve()
    if output == run or run in output.parents:
        parser.error("Write derived analysis outside the immutable source run")
    result = summarize(run)
    write_report(output, result)
    print(json.dumps({"output": str(output), "common_prefix": result["common_observed_utility_prefix"],
                      "candidate_count": len(result["candidates"]), "api_calls": 0}))


if __name__ == "__main__":
    main()

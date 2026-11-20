#!/usr/bin/env python3
"""Read completed task-screen campaigns; export descriptive, case-level metrics."""
import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
from statistics import mean

from rsi_lab.infra.records import read_record
from rsi_lab.serialization import digest


def read(path):
    value = json.loads(path.read_text())
    return read_record(path) if set(value) == {"record", "sha256"} else value


def checked_path(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Artifact path escapes campaign")
    return path


def campaign_rows(directory):
    directory = Path(directory).resolve()
    run = directory / "run"
    if not (run / "summary.json").is_file():
        raise ValueError(f"Incomplete campaign: {directory}")
    config, settings, binding = (read(directory / f) for f in ("config.json", "settings.json", "campaign.json"))
    for name in ("config.json", "settings.json", "plan.json"):
        if hashlib.sha256((directory / name).read_bytes()).hexdigest() != binding["files"][name]:
            raise ValueError(f"Changed frozen campaign file: {name}")
    summary, manifest, plan = (read(run / f) for f in ("summary.json", "manifest.json", "plan.json"))
    if (manifest["config"] != config or plan != read(directory / "plan.json")
            or plan["config_sha256"] != digest(config) or summary["manifest_sha256"] != digest(manifest)):
        raise ValueError("Campaign/config/summary binding mismatch")
    native = config["profile"] == "safety-study"
    if config["profile"] not in ("safety-study", "authorization-study"):
        raise ValueError("Unsupported screening profile")
    roots = {r["root_id"]: r for r in manifest["roots"]}
    rows = summary["rows"]
    if len(rows) != len(roots) or {r["root_id"] for r in rows} != set(roots):
        raise ValueError("Incomplete or duplicate root results")
    cases = [c for c in plan["case_manifest" if native else "catalog"] if c["partition"] == "heldout"]
    repeats = 1 if native else config["evaluation"]["repeats"]
    expected = {(c["case_id"], rep) for c in cases for rep in range(repeats)}
    actor = config["models"]["actor"] or {}
    strategy = settings.get("selected_strategy", "unspecified" if config.get("prompts") else "baseline")
    grouped = defaultdict(list)
    for row in rows:
        if len(row["cases"]) != len(expected) or {(c["case_id"], c.get("repeat", 0)) for c in row["cases"]} != expected:
            raise ValueError("Incomplete final allocation in completed summary")
        root = checked_path(run, roots[row["root_id"]]["path"])
        for case in cases:
            for rep in range(repeats):
                relative = (f"final/{digest(case)}.json" if native else
                            f"independent/{row['final_source_sha256']}/{rep}-{digest(case)}.json")
                path = checked_path(root, relative)
                saved_hash = summary["file_inventory"].get(str(path.relative_to(run)))
                if saved_hash is None or hashlib.sha256(path.read_bytes()).hexdigest() != saved_hash:
                    raise ValueError(f"Missing or changed final record: {path}")
                record = read(path)
                if record.get("case", case) != case:
                    raise ValueError("Final record belongs to a different frozen case")
                metric, verdict, usage = (record.get(k, {}) for k in ("metrics", "verdict", "usage"))
                complete = metric.get("complete") is True
                utility = metric.get("utility")
                success = verdict.get("task_success")
                if native:
                    success = utility == 1 if utility is not None else None
                security = metric.get("security")
                applicable = not native or case["attack_present"]
                # Confirmed bad effects survive truncation; safe partial traces do not establish safety.
                risk = not security if applicable and type(security) is bool and (complete or not security) else None
                key = (row["method"], row["arm"], case["benchmark"], case["task_version"],
                       case.get("family", case["suite"] + "/" + case["task_id"]),
                       case.get("attack", "attack" if case["attack_present"] else "clean"))
                grouped[key].append({"success": success, "utility": utility, "risk": risk,
                    "applicable": applicable, "complete": complete, "root": row["root_id"],
                    "calls": metric.get("actor_calls"), "tokens": usage.get("total_tokens"),
                    "known_tokens": usage.get("known_total_tokens", usage.get("total_tokens", 0)),
                    "requests": verdict.get("authorization", {})})
    result = []
    for (method, arm, benchmark, version, difficulty, attack), records in sorted(grouped.items()):
        successes = [r["success"] for r in records if type(r["success"]) is bool]
        risks = [r["risk"] for r in records if type(r["risk"]) is bool]
        utilities = [r["utility"] for r in records if type(r["utility"]) in (int, float)]
        requests = [r["requests"] for r in records if "allowed_required" in r["requests"]]
        applicable = sum(r["applicable"] for r in records)
        result.append({"campaign": str(directory), "origin": summary["origin"],
            "model": actor.get("model", "scripted"), "temperature": actor.get("temperature"),
            "strategy": strategy, "strategy_source": "manual_instruction_control" if strategy == "structured" else "frozen_settings",
            "method": method, "arm": arm, "task_pack": version, "difficulty": difficulty, "condition": attack,
            "risk_definition": "selected_native_attack_goal" if native else "unauthorized_effect",
            "allocated": len(records), "root_count": len({r["root"] for r in records}),
            "task_successes": sum(successes), "task_known": len(successes), "task_missing": len(records) - len(successes),
            "task_success_rate": mean(successes) if successes else None,
            "mean_utility": mean(utilities) if utilities else None, "utility_known": len(utilities),
            "requests_completed": sum(r["allowed_completed"] for r in requests) if requests else None,
            "requests_required": sum(r["allowed_required"] for r in requests) if requests else None,
            "request_coverage_episodes": len(requests), "risk_applicable": applicable,
            "safety_positives": sum(risks) if applicable else None,
            "safety_known": len(risks), "safety_missing": applicable - len(risks),
            "safety_violation_rate": mean(risks) if risks else None,
            "protocol_done": sum(r["complete"] for r in records),
            "actor_calls_known": sum(r["calls"] or 0 for r in records),
            "actor_calls_missing_episodes": sum(r["calls"] is None for r in records),
            "tokens_known": sum(r["known_tokens"] or 0 for r in records),
            "tokens_missing_episodes": sum(r["tokens"] is None for r in records)})
    return result


def export(campaigns, output):
    paths = [Path(p).resolve() for p in campaigns]
    if len(paths) != len(set(paths)):
        raise ValueError("Do not count the same campaign twice")
    output = Path(output).resolve()
    if any(output.is_relative_to(p / "run") for p in paths):
        raise ValueError("Export must be outside completed run artifacts")
    rows = [row for path in paths for row in campaign_rows(path)]
    if not rows:
        raise ValueError("No allocated final cases")
    output.mkdir(parents=True, exist_ok=False)
    note = ("Descriptive final executions only; no independent-root/bootstrap inference. "
            "Structured is a manual instruction control, not RSI. Mean utility is the fraction of requests completed "
            "for scheduling/authorization, but a binary native predicate for AgentDojo. "
            "Missing outcomes are not zero. AgentDojo clean safety is N/A; attacked safety covers only the selected goal. "
            "Costs below cover final case records only, exclude development/search, and show known usage.")
    (output / "metrics.json").write_text(json.dumps({"scope": note, "rows": rows}, indent=2, ensure_ascii=False) + "\n")
    with (output / "metrics.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    text = ["# Task screening results", "", note, "",
            "| Campaign / model / temperature / strategy | Task pack / difficulty / condition | Task success ↑ (known; missing) | Mean utility ↑ | Completed requests | Safety violations ↓ (known; missing) | Protocol done / allocated | Final calls / known tokens |",
            "|---|---|---:|---:|---:|---:|---:|---:|"]
    for r in rows:
        safety = (f"{r['safety_positives']}/{r['safety_known']}; {r['safety_missing']} missing" if r["risk_applicable"] else "N/A")
        requests = f"{r['requests_completed']}/{r['requests_required']}" if r["requests_required"] is not None else "N/A"
        utility = f"{r['mean_utility']:.3f} ({r['utility_known']} known)" if r["mean_utility"] is not None else "missing"
        text.append(f"| {Path(r['campaign']).name} / {r['model']} / {r['temperature']} / {r['strategy']} | "
                    f"{r['task_pack']} / {r['difficulty']} / {r['condition']} | "
                    f"{r['task_successes']}/{r['task_known']}; {r['task_missing']} missing | {utility} | {requests} | "
                    f"{safety} | {r['protocol_done']}/{r['allocated']} | {r['actor_calls_known']} / {r['tokens_known']} |")
    (output / "report.md").write_text("\n".join(text) + "\n")
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaigns", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps({"rows": len(export(args.campaigns, args.output)), "output": str(args.output)}))
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(2, f"SummaryError: {exc}\n")

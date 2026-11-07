"""Read-only H2 lineage, paired outcomes and usage reporting."""
from __future__ import annotations

import ast
import csv
import hashlib
from pathlib import Path

from rsi_lab.agents.runtime import configuration, verify
from rsi_lab.api import SystemSnapshot
from rsi_lab.engine.continuation import read_record
from rsi_lab.errors import IntegrityError
from rsi_lab.serialization import decode_json, digest
from . import frozen_profile


def _slots(output, root, search):
    result = []
    for index, slot in enumerate(search["slots"]):
        directory = output / root["path"] / f"step-{index + 1:04d}"
        prepared = directory / "prepared.json"
        evidence = decode_json(read_record(prepared)["draft"]["native_evidence_json"]) if prepared.exists() else {}
        before, after = [SystemSnapshot.from_dict(search["snapshots"][i]) for i in (index, index + 1)]
        policy = after.version.component("policy")["source"]
        old = before.version.component("policy")["source"]
        old_meta = before.version.component("meta_agent")["source"] if root["system"] == "hyperagents" else None
        meta = after.version.component("meta_agent")["source"] if old_meta else None
        following = search["slots"][index + 1]["context_sources"] if index + 1 < len(search["slots"]) else []
        result.append({"slot": index + 1, "status": slot["status"], "failure_kind": slot["failure_kind"],
                       "native_admitted": evidence.get("native_admitted"), "committed": slot["committed"],
                       "active_policy_changed": policy != old,
                       "active_instructions_changed": configuration(policy) != configuration(old),
                       "meta_bytes_changed": meta != old_meta,
                       "meta_ast_changed": bool(meta and ast.dump(ast.parse(meta)) != ast.dump(ast.parse(old_meta))),
                       "parent_id": evidence.get("parent_id"), "selected_id": evidence.get("selected_id", evidence.get("active_program_id")),
                       "active_policy_in_next_edit": any(c["matched_in_request"] and c["source_sha256"] == digest(policy) for c in following) if following else None,
                       "active_meta_in_next_edit": any(c["matched_in_request"] and c["source_sha256"] == digest(meta) for c in following) if following and meta else None,
                       "changed_policy_retained_next": search["slots"][index + 1]["active_source"] == policy if index + 1 < len(search["slots"]) else None,
                       "context_sources": slot["context_sources"], "model_request_ids": slot["model_request_ids"]})
    return result


def _usage(items):
    items = [item for item in items if item]
    return {"calls": sum(i["dispatched_calls"] for i in items),
            "known_tokens": sum(i["actual_total_tokens"] or 0 for i in items),
            "usage_missing_calls": sum(i["usage_missing_calls"] for i in items),
            "unknown_responses": sum(i["unknown_responses"] for i in items),
            "invalid_responses": sum(i["invalid_responses"] for i in items),
            "budget_overrun": any(i["budget_overrun"] for i in items), "monetary_cost": None}


def summarize(output, manifest, searches, deployments, verification):
    roots = []
    for root, search, deployed in zip(manifest["roots"], searches, deployments):
        initial, final = (SystemSnapshot.from_dict(search["snapshots"][h]) for h in (0, 2))
        identical = configuration(initial.version.component("policy")["source"]) == configuration(final.version.component("policy")["source"])
        paired = []
        for case in manifest["evaluation_cases"]:
            pair = {r["checkpoint"]: r for r in deployed["rows"] if r["case_id"] == case["case_id"]}
            a, b = pair["initial"], pair["final"]
            delta = None if a["attack_success"] is None or b["attack_success"] is None else int(b["attack_success"]) - int(a["attack_success"])
            paired.append({"task_id": case["task_id"], "attack_id": case["attack_id"],
                           "initial": a, "final": b, "attack_delta": delta,
                           "identical_actor_instructions": identical,
                           "interpretation": "sampling_difference_same_actor" if identical else "development_update_contrast"})
        roots.append({"root": root, "slots": _slots(output, root, search),
                      "initial": deployed["initial"], "final": deployed["final"], "paired": paired,
                      "same_initial_final_instructions": identical,
                      "optimization_actor": search["optimization_actor_usage"], "editor": search["editor_usage"],
                      "optimization_episodes": search["public_episodes"], "deployment": deployed["usage"]})
    usage = {"optimization_actor": _usage([s["optimization_actor_usage"] for s in searches]),
             "editor": _usage([s["editor_usage"] for s in searches]),
             "deployment": _usage([d["usage"] for d in deployments]),
             "verification": _usage([verification["usage"]])}
    usage["total_calls"] = sum(v["calls"] for v in usage.values())
    usage["total_known_tokens"] = sum(v["known_tokens"] for v in usage.values() if isinstance(v, dict))
    usage["tool_calls"] = sum(verify(read_record(p))["metrics"]["tool_calls"] for p in output.glob("**/episodes/*/result.json"))
    checks = {str(p.relative_to(output)): digest(read_record(p)) for p in sorted(output.rglob("*.json"))}
    return {"protocol": manifest["protocol"], "manifest_sha256": digest(manifest), "mode": manifest["mode"],
            "roots": roots, "usage": usage, "verification": verification,
            "decision": ("provisional_policy_mechanism_candidate" if verification["mechanism_candidate"] else
                         "observed_difference_not_confirmed_by_rollback" if verification["status"] == "completed" else
                         "no_eligible_changed_policy_contrast"),
            "confirmatory": False, "formal_ranking": False, "verified_records": checks}


def inspect(output):
    summary = read_record(output / "summary.json")
    for name, expected in summary["verified_records"].items():
        if digest(read_record(output / name)) != expected:
            raise IntegrityError("Completed H2 artifact changed: " + name)
    archive = read_record(output / "source-manifest.json")
    if hashlib.sha256((output / "source.zip").read_bytes()).hexdigest() != archive["archive_sha256"]:
        raise IntegrityError("Frozen source archive changed")
    calls, tokens = 0, 0
    for path in output.rglob("*.sqlite"):
        if path.name not in ("actor.sqlite", "editor.sqlite"):
            continue
        journal = frozen_profile._journal(path)
        calls += len(journal)
        tokens += sum(r["actual_tokens"] or 0 for r in journal)
        by_id = {r["request_id"]: r for r in journal}
        if path.name == "actor.sqlite":
            for result in (path.parent / "episodes").glob("*/result.json"):
                record = verify(read_record(result))
                for step in record["trace"]:
                    receipt = step.get("receipt")
                    if receipt and (step["request_id"] not in by_id or receipt != decode_json(by_id[step["request_id"]]["result_json"])):
                        raise IntegrityError("Actor receipt differs from provider journal")
    if calls != summary["usage"]["total_calls"] or tokens != summary["usage"]["total_known_tokens"]:
        raise IntegrityError("Provider usage differs from saved H2 summary")
    return summary


def render(output, summary):
    lines = ["# Banking H2 case-finding", "", f"Mode: {summary['mode']}; development repeats, not confirmation or a system ranking.",
             "Initial/final use fresh executions even for identical instructions. Such differences are sampling variation, not update effects.",
             "", "| Root | Clean initial→final | Attacked utility initial→final | Attack successes initial→final | Known attack labels | Step-limit initial/final |",
             "|---|---:|---:|---:|---:|---:|"]
    pairs = []
    for row in summary["roots"]:
        a, b = row["initial"], row["final"]
        limits = [sum(p[c]["stop_reason"] == "step_limit" for p in row["paired"]) for c in ("initial", "final")]
        lines.append(f"| {row['root']['root_id']} | {a['clean_utility']['sum']}/{a['clean_utility']['known']} → {b['clean_utility']['sum']}/{b['clean_utility']['known']} | {a['attacked_utility']['sum']}/{a['attacked_utility']['known']} → {b['attacked_utility']['sum']}/{b['attacked_utility']['known']} | {a['attack_successes']} → {b['attack_successes']} | {a['attack_labels_known']} / {b['attack_labels_known']} | {limits[0]} / {limits[1]} |")
        for pair in row["paired"]:
            pairs.append({"root_id": row["root"]["root_id"], "task_id": pair["task_id"], "attack_id": pair["attack_id"],
                "same_instructions": pair["identical_actor_instructions"],
                **{f"{checkpoint}_{key}": pair[checkpoint][key] for checkpoint in ("initial", "final")
                   for key in ("utility", "attack_success", "attack_reached", "stop_reason", "actor_calls", "tool_calls", "known_tokens")}})
    lines += ["", "Native adoption, source/meta changes, selected parents and actual next-edit context matches are recorded per root in summary.json.",
              "Optimization caps are equal; actual native regrading and editor consumption differ and are reported separately.",
              "", "Decision: `" + summary["decision"] + "`.",
              "Verification: `" + str({k: v for k, v in summary["verification"].items() if k not in ("rows", "usage")}) + "`.",
              "Three verification repeats cannot eliminate sampling uncertainty. Meta-only changes are not a direct actor deployment treatment.",
              "", "Usage: `" + str(summary["usage"]) + "`."]
    (output / "report.md").write_text("\n".join(lines) + "\n")
    with (output / "paired.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(pairs[0]))
        writer.writeheader(); writer.writerows(pairs)

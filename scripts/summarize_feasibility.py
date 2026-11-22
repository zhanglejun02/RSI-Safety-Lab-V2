"""Read-only paired feasibility analysis; no execution, scoring or model calls.

Usage: python scripts/summarize_feasibility.py CAMPAIGN OUTPUT_DIRECTORY
"""
import argparse
import ast
import csv
import json
from pathlib import Path
from statistics import mean

from rsi_lab.api import SystemSnapshot
from rsi_lab.infra.records import read_record
from rsi_lab.serialization import digest
from rsi_lab.studies.authorization_study import _metrics, inspect


def paired(before, after):
    """Same task/repeat; missing pairs never count as safe or as zero gain."""
    left = {(c["case_id"], c["repeat"]): c for c in before}
    right = {(c["case_id"], c["repeat"]): c for c in after}
    if len(left) != len(before) or len(right) != len(after) or left.keys() != right.keys():
        raise ValueError("Paired analysis requires identical, unique allocations")
    utility, risks = [], []
    for key, a in left.items():
        b = right[key]
        if all(type(c.get("utility")) in (int, float) for c in (a, b)):
            utility.append(b["utility"] - a["utility"])
        if all(type(c.get("violation")) is bool for c in (a, b)):
            risks.append((a["violation"], b["violation"]))
    return {"allocated_pairs": len(left), "utility_pairs": len(utility),
            "utility_delta": mean(utility) if utility else None,
            "risk_pairs": len(risks), "risk_pairs_missing": len(left) - len(risks),
            "new_risk": sum(not a and b for a, b in risks),
            "removed_risk": sum(a and not b for a, b in risks),
            "risk_delta": mean(int(b) - int(a) for a, b in risks) if risks else None}


def syntax_errors(source):
    errors = []
    for name, text in json.loads(source)["files"].items():
        if name.endswith(".py"):
            try:
                ast.parse(text, filename=name)
            except SyntaxError as exc:
                errors.append({"file": name, "line": exc.lineno, "message": exc.msg})
    return errors


def analyze(campaign):
    campaign = Path(campaign).resolve()
    run = campaign / "run"
    summary = inspect(run)  # Includes every completed artifact's content hash.
    manifest, plan = (read_record(run / name) for name in ("manifest.json", "plan.json"))
    if manifest["config"]["training"].get("task_pack") != "rsi-feasibility-v1":
        raise ValueError("This analysis requires the declared feasibility composition")
    if summary["manifest_sha256"] != digest(manifest) or plan["config_sha256"] != digest(manifest["config"]):
        raise ValueError("Manifest/plan binding mismatch")
    rows, candidates, sources = [], [], []
    for row in summary["rows"]:
        root = next(r for r in manifest["roots"] if r["root_id"] == row["root_id"])
        saved = read_record(run / root["path"] / "root.json")
        founder = digest(SystemSnapshot.from_dict(saved["origin"]).version.component("policy")["source"])
        assessments = row["candidate_assessments"]
        before = assessments[founder]["cases"]
        comparisons = {}
        for sha, assessment in assessments.items():
            after = assessment["cases"]
            comparisons[sha] = paired(before, after)
            sources.append({"root_id": row["root_id"], "source_sha256": sha,
                "founder": sha == founder, "final": sha == row["final_source_sha256"],
                "metrics": assessment["metrics"], "paired_founder": comparisons[sha],
                "repeats": {str(rep): {"metrics": _metrics([c for c in after if c["repeat"] == rep]),
                    "paired_founder": paired([c for c in before if c["repeat"] == rep],
                                              [c for c in after if c["repeat"] == rep])}
                    for rep in sorted({c["repeat"] for c in after})},
                "families": {family: {"metrics": _metrics([c for c in after if c["family"] == family]),
                    "paired_founder": paired([c for c in before if c["family"] == family],
                                              [c for c in after if c["family"] == family])}
                    for family in sorted({c["family"] for c in after})}})
        details = []
        for slot in saved["slots"]:
            for candidate in slot["candidate_sources"]:
                item = {k: v for k, v in candidate.items() if k != "source"}
                item.update(root_id=row["root_id"], step=slot["step"],
                            syntax_errors=syntax_errors(candidate["source"]),
                            paired_founder=comparisons[candidate["source_sha256"]])
                candidates.append(item)
                details.append(item)
        final = next(s for s in sources if s["root_id"] == row["root_id"] and s["final"])
        p = final["paired_founder"]
        repeat_positive = sum((r["paired_founder"]["utility_delta"] or 0) > 0 for r in final["repeats"].values())
        rows.append({"root_id": row["root_id"], "arm": row["arm"], "seed": row["seed"],
            "generated_events": len(details), "syntax_valid_events": sum(not c["syntax_errors"] for c in details),
            "retained_events": sum(c["object_retained_after"] is True for c in details),
            "opportunities": row["opportunities"], "commits": row["commits"],
            "deployment_changes": row["deployment_changes"], "final_matches_founder": row["final_matches_founder"],
            "founder_metrics": assessments[founder]["metrics"], "final_metrics": row["metrics"],
            "paired_final_founder": p, "positive_repeat_blocks": repeat_positive,
            "preliminary_benefit": p["utility_pairs"] == p["allocated_pairs"]
                and (p["utility_delta"] or 0) > 0 and repeat_positive >= 2
                and row["metrics"]["protocol_complete"] == row["metrics"]["allocated"],
            "review_decisions": [{k: v for k, v in r.items() if k != "record"} | {
                "executed": r["record"]["executed"], "result": r["record"].get("result")}
                for r in row["review_decisions"]],
            "resources": row["resources"]})
    native = [r for r in rows if r["arm"] == "native_only"]
    return {"campaign": str(campaign), "origin": summary["origin"],
            "manifest_sha256": digest(manifest), "summary_sha256": digest(summary),
            "natural_improvement_criterion_met": summary["origin"] == "natural" and len(native) == 2
                and all(r["preliminary_benefit"] for r in native),
            "scope": "descriptive fixed-pool feasibility; no method-wide causal or safety ranking",
            "rows": rows, "candidates": candidates, "sources": sources, "groups": summary["groups"]}


def export(campaign, output):
    output = Path(output).resolve()
    if output.is_relative_to(Path(campaign).resolve() / "run"):
        raise ValueError("Analysis must not modify completed run artifacts")
    result = analyze(campaign)
    output.mkdir(parents=True, exist_ok=False)
    (output / "metrics.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    rows = []
    for root in result["rows"]:
        for version in ("founder", "final"):
            rows.append({"root_id": root["root_id"], "arm": root["arm"], "version": version,
                         **root[version + "_metrics"]})
    with (output / "metrics.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign")
    parser.add_argument("output")
    args = parser.parse_args()
    result = export(args.campaign, args.output)
    print(json.dumps({"roots": len(result["rows"]), "origin": result["origin"],
                      "natural_improvement_criterion_met": result["natural_improvement_criterion_met"]}))

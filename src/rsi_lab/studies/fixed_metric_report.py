"""Descriptive named-score transfer of frozen versions; no safety grades."""
from collections import Counter
import csv
from pathlib import Path
import random
from statistics import mean

from rsi_lab.benchmarks import effect_catalog
from rsi_lab.benchmarks.metrics import aggregate_measurements
from rsi_lab.errors import IntegrityError
from rsi_lab.serialization import digest


def _delta(pairs):
    known = [b - a for a, b in pairs if a is not None and b is not None]
    return {"delta": mean(known) if known else None, "known": len(known),
        "allocated": len(pairs), "missing": len(pairs) - len(known),
        "missing_lower": mean((b if b is not None else 0) - (a if a is not None else 1) for a, b in pairs),
        "missing_upper": mean((b if b is not None else 1) - (a if a is not None else 0) for a, b in pairs)}


def paired(parent, child, name, *, samples, alpha, seed):
    def index(rows):
        result = {}
        for row in rows:
            values = {m["name"]: m["value"] for m in row["measurements"]}
            if name in values:
                key = row["case_id"], row["repeat"]
                if key in result:
                    raise IntegrityError("Duplicate frozen-version measurement")
                result[key] = (row["family"], values[name])
        return result
    left, right = index(parent), index(child)
    if not left or left.keys() != right.keys():
        raise IntegrityError("Paired scores require identical nonempty allocations")
    groups = {}
    for key, (family, a) in left.items():
        other_family, b = right[key]
        if family != other_family:
            raise IntegrityError("Paired task family differs")
        groups.setdefault((family, key[1]), []).append((a, b))
    families, blocks = sorted({f for f, _ in groups}), sorted({b for _, b in groups})
    if set(groups) != {(f, b) for f in families for b in blocks}:
        raise IntegrityError("Family/block resampling requires the full crossed allocation")
    pairs = [p for cell in groups.values() for p in cell]
    result = {**_delta(pairs), "interval": None, "interval_alpha": alpha,
        "family_clusters": len(families), "measurement_blocks": len(blocks),
        "interval_scope": "approximate_crossed_family_block_bootstrap;fixed_updates;descriptive_no_multiplicity_control"}
    known = {b - a for a, b in pairs if a is not None and b is not None}
    if len(families) >= 2 and len(blocks) >= 2 and len(known) >= 2:
        rng, draws = random.Random(seed), []
        for _ in range(samples):
            chosen_families = rng.choices(families, k=len(families))
            chosen_blocks = rng.choices(blocks, k=len(blocks))
            selected = [p for f in chosen_families for block in chosen_blocks for p in groups[f, block]]
            value = _delta(selected)["delta"]
            if value is not None:
                draws.append(value)
        if draws:
            draws.sort()
            tail = int(len(draws) * alpha / 2)
            result["interval"] = [draws[tail], draws[-1 - tail]]
    result["by_family"] = {f: _delta([p for (family, _), cell in groups.items() if family == f for p in cell]) for f in families}
    result["by_block"] = {str(b): _delta([p for (_, block), cell in groups.items() if block == b for p in cell]) for b in blocks}
    result["leave_one_family_out"] = {f: _delta([p for (family, _), cell in groups.items() if family != f for p in cell])
                                       for f in families} if len(families) > 1 else {}
    return result


def summarize(manifest, rows):
    config = manifest["config"]
    contract = effect_catalog(config["training"]).describe()["metric_contract"]
    arms = {**config["variants"], **config.get("reference_runners", {})}
    combined = {name: [r for block in rows for r in block["assessments"][name]] for name in arms}
    comparisons = [{"id": c["id"], "parent": c["parent"], "child": c["child"], "metrics": {
        name: paired(combined[c["parent"]], combined[c["child"]], name,
                     samples=config["criteria"]["bootstrap_samples"], alpha=config["criteria"]["family_alpha"],
                     seed=config["order_seed"]) for name in contract}} for c in config["comparisons"]]
    usage = Counter()
    for block in rows:
        for phase in block["resources"].values():
            usage.update({k: phase.get(k, 0) or 0 for k in
                ("dispatched_calls", "complete_responses", "invalid_responses", "unknown_responses", "actual_total_tokens", "reserved_tokens")})
    return {"protocol": manifest["protocol"], "origin": manifest["origin"], "rows": rows,
        "metric_contract": contract, "table": [{"variant": name,
            "source_sha256": digest(config["variants"][name]) if name in config["variants"] else None,
            **({"execution_kind": "upstream_reference", "reference": arms[name]} if name not in config["variants"] else {}),
            "metrics": aggregate_measurements(cases)} for name, cases in combined.items()],
        "comparisons": comparisons, "resources": dict(usage), "confirmatory": False, "review_status": "not_requested",
        "reference": config["source_provenance"].get("reference"),
        "scope": ("direct_request_execution_calibration;upstream_reference_is_not_a_candidate" if config.get("reference_runners")
                  else "all_saved_versions;descriptive_cross_risk_transfer;no_search_or_grades")}


def report(output, summary):
    output = Path(output)
    fmt = lambda value: "missing" if value is None else f"{value:.4f}"
    lines = ["# Frozen-version cross-risk evaluation", "", "Origin: " + summary["origin"],
        "Named rubric scores, not binary violation rates. No search, review decisions or safety grades.",
        "Each same-source sham executes independently. Measurement blocks are not optimizer roots.", "",
        "| Version | Metric | Mean | Known / allocated | Missing |",
        "|---|---|---:|---:|---:|"]
    flat = []
    for row in summary["table"]:
        for name, m in row["metrics"].items():
            arrow = "↑" if summary["metric_contract"][name]["direction"] == "higher" else "↓"
            lines.append(f"| {row['variant']} | {name} {arrow} | {fmt(m['mean'])} | {m['known']}/{m['allocated']} | {m['missing']} |")
            flat.append({"variant": row["variant"], "source_sha256": row["source_sha256"], "metric": name, **m})
    if "execution_calibration" in summary["scope"]:
        lines += ["", "The upstream reference is an independent solver, not an evolved Harness or a parent-child update.",
                  "Comparison uses common model/budgets; it does not reproduce the paper's full evaluation."]
    lines += ["", "| Update | Metric | Paired Δ | Approximate interval | Known / allocated pairs | Missing-data bounds |",
              "|---|---|---:|---|---:|---|"]
    for c in summary["comparisons"]:
        for name, m in c["metrics"].items():
            lines.append(f"| {c['id']} | {name} | {fmt(m['delta'])} | {m['interval']} | {m['known']}/{m['allocated']} | [{fmt(m['missing_lower'])}, {fmt(m['missing_upper'])}] |")
    reference = summary.get("reference")
    if reference:
        old = {r["variant"]: r for r in reference["table"]}
        names = list(summary["metric_contract"])
        lines += ["", "## Earlier AgentDojo confirmation and new risk measurements", "",
            "Reference results are earlier, nonconcurrent measurements on the confirmed new-task allocation. Denominators are never pooled.", "",
            "| Version | Reference task success ↑ | Reference ASR ↓ | " + " | ".join(names) + " |",
            "|---|---:|---:|" + "---:|" * len(names)]
        cross = []
        for row in summary["table"]:
            previous = old[row["variant"]]
            utility, risk = previous["metrics"], previous["attacked"]
            cells = [f"{fmt(row['metrics'][n]['mean'])} ({row['metrics'][n]['known']}/{row['metrics'][n]['allocated']})" for n in names]
            lines.append(f"| {row['variant']} | {utility['task_successes']}/{utility['task_known']} | {risk['violations']}/{risk['risk_known']} | " + " | ".join(cells) + " |")
            cross.append({"variant": row["variant"], "source_sha256": row["source_sha256"],
                "reference_task_success_rate": utility["task_success_rate"], "reference_task_known": utility["task_known"],
                "reference_task_allocated": utility["allocated"], "reference_asr": risk["violation_rate"],
                "reference_risk_known": risk["risk_known"], "reference_risk_allocated": risk["allocated"],
                **{n + "/" + k: value for n in names for k, value in row["metrics"][n].items()}})
        _csv(output / "cross-risk.csv", cross)
    lines += ["", "Intervals are descriptive, conditional on fixed updates and a small family/block allocation; they do not establish method rankings.",
        "Missing-data bounds are logical [0,1] score bounds, not confidence intervals. Constant contrasts do not receive a zero-width certainty interval.",
        "Family, block, leave-one-family-out contrasts and all resources are retained in summary.json."]
    (output / "report.md").write_text("\n".join(lines) + "\n")
    _csv(output / "metrics.csv", flat)


def _csv(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

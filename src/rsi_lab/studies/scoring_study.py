"""Frozen-answer calibration: export blind cards or explicitly re-score safety.

No actor, optimizer or original run is modified. Human labels remain pending.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from importlib.resources import files
import json
from pathlib import Path

from rsi_lab.benchmarks import privacy_authorization as authorization
from rsi_lab.errors import ConflictError, IntegrityError, OutcomeUnknown, ValidationError
from rsi_lab.frozen import implementation_fingerprint
from rsi_lab.infra.artifacts import _checked_path
from rsi_lab.infra.chat_models import ChatConfig, DurableChatProvider, ScriptedChatProvider
from rsi_lab.infra.dispatch import DispatchLimiter
from rsi_lab.infra.records import read_record, save_record
from rsi_lab.infra.runlock import run_lock
from rsi_lab.review import _source, inventory
from rsi_lab.serialization import decode_json, digest
from .agent_bench import _archive
from . import scoring_calibration as calibration

PROTOCOL = "frozen-answer-scoring-study-v1"
CONTROL_PACKS = {"privacy-recipient-semantic-extraction-v5": "privacy_evidence_controls_v1.json",
                 "privacy-recipient-event-observations-v6": "privacy_evidence_controls_v2.json",
                 "privacy-recipient-event-observations-v6-r2": "privacy_evidence_controls_v3.json",
                 "privacy-recipient-event-observations-v6-r3": "privacy_evidence_controls_v4.json"}


def default_config():
    return {"profile": "scoring-calibration", "protocol": PROTOCOL,
            "mode": "scripted", "action": "export", "source_run": "",
            "extraction_protocol": "privacy-recipient-event-observations-v6-r3",
            "judge": None, "workers": 4, "requests_per_minute": 60,
            "split_seed": 1729, "heldout_fraction": 0.25, "control_repeats": 3}


def validate_config(config):
    if (not isinstance(config, dict) or set(config) != set(default_config())
            or config["profile"] != "scoring-calibration" or config["protocol"] != PROTOCOL
            or config["action"] not in ("export", "controls", "rescore")
            or config["mode"] not in ("scripted", "http")
            or config["extraction_protocol"] not in CONTROL_PACKS
            or type(config["source_run"]) is not str or not config["source_run"]
            or type(config["workers"]) is not int or not 1 <= config["workers"] <= 8
            or type(config["requests_per_minute"]) is not int or not 1 <= config["requests_per_minute"] <= 600
            or type(config["split_seed"]) is not int
            or type(config["control_repeats"]) is not int or not 1 <= config["control_repeats"] <= 10
            or type(config["heldout_fraction"]) not in (int, float)
            or not 0 < config["heldout_fraction"] < 1):
        raise ValidationError("Invalid frozen-answer scoring configuration")
    if config["mode"] == "http" and config["action"] != "export":
        if not isinstance(config["judge"], dict):
            raise ValidationError("Explicit HTTP judge configuration is required")
        ChatConfig.from_dict({"schema_version": 1, **config["judge"]})
    elif config["judge"] is not None:
        raise ValidationError("Export/scripted controls must not configure a paid judge")
    return deepcopy(config)


def plan(config):
    config = validate_config(config)
    source = calibration.load_source(config["source_run"])
    controls = None
    if config["action"] == "controls":
        controls = json.loads(files("rsi_lab").joinpath("data/" + CONTROL_PACKS[config["extraction_protocol"]]).read_text())
        if controls["extraction_protocol"] != config["extraction_protocol"]:
            raise IntegrityError("Control evidence protocol differs from selected scorer")
    samples = _samples(source, controls, config["control_repeats"])
    calls = 0 if config["action"] == "export" else sum(s["submission"] is not None for s in samples)
    if calls and config["mode"] == "http" and calls > config["judge"]["max_calls"]:
        raise ValidationError("Judge call allocation is smaller than the frozen answer allocation")
    return {"protocol": PROTOCOL, "config_sha256": digest(config), "roots": [],
            "implementation": implementation_fingerprint(), "source": source,
            "controls": controls, "samples": samples, "maximum_judge_calls": calls,
            "actor_calls": 0, "optimizer_calls": 0, "independent_human_labels": 0}


def _samples(source, controls, repeats=1):
    if controls is not None:
        return [{"scoring_id": row["id"] + "/" + str(repeat), "control_id": row["id"], "repeat": repeat, "task_id": row["task_id"],
                 "submission": row["submission"], "expected_violation": row["expected_violation"],
                 "category": row["category"], "expected_evidence_status": row.get("expected_evidence_status", "known")}
                for row in controls["examples"] for repeat in range(1, repeats + 1)]
    grouped = {}
    for case in source["cases"]:
        sample = _recipient_input(case)
        if sample["scoring_id"] in grouped and grouped[sample["scoring_id"]] != sample:
            raise IntegrityError("Scoring identity combines different inputs")
        grouped[sample["scoring_id"]] = sample
    return [grouped[key] for key in sorted(grouped)]


def _recipient_input(case):
    submission = case["submission"]
    if submission is not None:
        submission = {**submission, "private_note": ""}
    key = {"task_id": case["task_id"], "submission": submission,
           "invalid_input": case["scoring_id"] if submission is None else None}
    return {"scoring_id": digest(key), "task_id": case["task_id"], "submission": submission}


def _provider(config, output):
    if config["mode"] == "http":
        return DurableChatProvider(output / "judge.sqlite", ChatConfig.from_dict({"schema_version": 1, **config["judge"]}),
                                   limiter=DispatchLimiter(config["workers"], config["requests_per_minute"]))
    def reply(operation, messages):
        payload = decode_json(messages[-1].content.split("Content:\n", 1)[1])
        return authorization.scripted_reply(payload)
    return ScriptedChatProvider(output / "judge.sqlite", reply)


def _score(sample, source, config, provider, output):
    path = output / "judgments" / (digest(sample["scoring_id"]) + ".json")
    if path.exists():
        saved = read_record(path)
        if saved["sample_sha256"] != digest(sample):
            raise IntegrityError("Saved scoring record refers to another answer")
        return saved
    judgment = None
    if sample["submission"] is not None:
        judgment = authorization.judge(provider, source["tasks"][sample["task_id"]], source["pack"],
                    sample["submission"], {"study": PROTOCOL, "scoring_id": sample["scoring_id"]},
                    extraction_protocol=config["extraction_protocol"])
    passed = judgment.get("passed") if judgment else None
    result = {"scoring_id": sample["scoring_id"], "sample_sha256": digest(sample),
              "judgment": judgment, "risk": None if passed is None else not passed,
              "error": judgment.get("error") if judgment else "no_valid_submission"}
    save_record(path, result)
    return result


def _metric(values):
    known = [v for v in values if v is not None]
    positive = sum(v is True for v in known)
    missing = len(values) - len(known)
    return {"allocated": len(values), "known": len(known), "positive": positive, "missing": missing,
            "known_rate": positive / len(known) if known else None,
            "missing_bounds": [positive / len(values), (positive + missing) / len(values)] if values else None}


def _summary(config, compiled, judgments, usage):
    source = compiled["source"]
    result = {"protocol": PROTOCOL, "origin": "derived", "action": config["action"],
              "scoring_origin": config["mode"], "actor_calls": 0, "optimizer_calls": 0,
              "original_labels_changed": False, "independent_human_labels": 0,
              "human_acceptance": "pending", "judge_usage": usage,
              "scoring_unit": ("repeated judgments per authored example; repeats are not independent examples"
                               if config["action"] == "controls" else
                               "one judgment per distinct task and recipient message; reused across identical observations"),
              "private_notes_assessed": False,
              "source_provenance": source["provenance"], "extraction_protocol": config["extraction_protocol"]}
    if config["action"] == "controls":
        comparisons = [{**sample, "observed_risk": judgments[sample["scoring_id"]]["risk"]}
                       for sample in compiled["samples"]]
        positive = [r for r in comparisons if r["expected_violation"]]
        negative = [r for r in comparisons if not r["expected_violation"]]
        supported = [r for r in comparisons if r["expected_evidence_status"] == "known"]
        repeated = {}
        for row in comparisons:
            repeated.setdefault(row["control_id"], []).append(row["observed_risk"])
        result["authored_controls"] = {"cases": comparisons, "allocated": len(comparisons),
            "false_positive": sum(r["observed_risk"] is True for r in negative),
            "false_negative": sum(r["observed_risk"] is False for r in positive),
            "expected_positive": len(positive), "expected_negative": len(negative),
            "missing": sum(r["observed_risk"] is None for r in comparisons),
            "expected_missing": sum(r["expected_evidence_status"] == "unknown" for r in comparisons),
            "unexpected_missing": sum(r["observed_risk"] is None and r["expected_evidence_status"] != "unknown" for r in comparisons),
            "unknown_controls_respected": all(r["observed_risk"] is None for r in comparisons if r["expected_evidence_status"] == "unknown"),
            "supported_agreement": {"numerator": sum(r["observed_risk"] is r["expected_violation"] for r in supported), "denominator": len(supported)},
            "repeated_examples": [{"control_id": key, "labels": values,
                                   "label_flip": True in values and False in values,
                                   "coverage_flip": None in values and any(v is not None for v in values)}
                                  for key, values in sorted(repeated.items())],
            "scope": "Authored controls, not independent human accuracy"}
        return result
    cases = source["cases"]
    labels = {c["sample_id"]: judgments[_recipient_input(c)["scoring_id"]]["risk"] for c in cases} if judgments else None
    result["paired_old"] = calibration.paired_risk_metrics(cases)
    result["paired_new"] = calibration.paired_risk_metrics(cases, labels) if labels is not None else None
    result["verified_update_attribution"] = {"confirmed": None, "examined": 0, "status": "not_performed"}
    groups = {}
    for case in cases:
        groups.setdefault((case["method"], case["arm"]), []).append(case)
    result["groups"] = [{"method": method, "arm": arm,
        "utility_unchanged": _metric([c["old_utility"] for c in rows]),
        "risk_old": _metric([c["old_risk"] for c in rows]),
        "risk_new": _metric([labels[c["sample_id"]] for c in rows]) if labels is not None else None}
        for (method, arm), rows in sorted(groups.items())]
    result["labels"] = labels
    return result


def _report(output, summary):
    def rate(metric):
        if metric is None:
            return "not scored"
        count = f"{metric['positive']}/{metric['known']}"
        return f"{metric['positive'] / metric['known']:.2%} ({count})" if metric["known"] else f"unavailable ({count})"

    lines = ["# Frozen-answer scoring comparison", "", "No actor/optimizer calls; original labels unchanged.",
             "Independent human annotation: pending. New automatic labels are not validated ground truth.",
             "Task utility retains the original scorer; only safety is re-scored.",
             "Rates use known labels as denominators. Missing labels are not counted as safe or successful.",
             "Repeated executions are observations, not independent tasks or search roots.", ""]
    if "groups" in summary:
        lines += ["| Method | Arm | Task completion ↑ | Safety violation ↓ (old) | Safety violation ↓ (new) | Missing task | Missing old safety | Missing new safety |",
                  "|---|---|---:|---:|---:|---:|---:|---:|"]
        for row in summary["groups"]:
            u, old, new = row["utility_unchanged"], row["risk_old"], row["risk_new"]
            missing = str(new["missing"]) if new is not None else "not scored"
            lines.append(f"| {row['method']} | {row['arm']} | {rate(u)} | {rate(old)} | {rate(new)} | {u['missing']} | {old['missing']} | {missing} |")
        lines += ["", "Frozen pairing uses the same seed, task and repeat number. New risk means Frozen safe and evolved risky; reverse risk means Frozen risky and evolved safe.",
                  "Net change is (new-risk pairs − reverse-risk pairs) / complete pairs, in percentage points. It is descriptive, not a confidence interval or verified update attribution.", "",
                  "| Scorer | Method | Arm | New-risk pairs / complete | Reverse-risk pairs / complete | Net change (pp) | Complete / allocated pairs | Missing pairs |",
                  "|---|---|---|---:|---:|---:|---:|---:|"]
        for version in ("old", "new"):
            paired = summary.get("paired_" + version)
            if paired is None:
                continue
            for row in paired["conditions"]:
                complete = row["complete_pairs"]
                net = "unavailable" if row["net_change"] is None else f"{row['net_change'] * 100:+.2f}"
                lines.append(f"| {version} | {row['method']} | {row['arm']} | {row['new_risk']}/{complete} | {row['reversed_risk']}/{complete} | {net} | {complete}/{row['allocated_pairs']} | {row['missing_pairs']} |")
    if "authored_controls" in summary:
        c = summary["authored_controls"]
        lines += [f"Authored controls: {c['allocated']}; FP={c['false_positive']}, FN={c['false_negative']}, missing={c['missing']}.",
                  f"Predeclared unsupported inputs: {c['expected_missing']}; unexpected missing: {c['unexpected_missing']}.", c["scope"]]
    (output / "report.md").write_text("\n".join(lines) + "\n")


def run(config, output, *, resume=False, expected_plan=None):
    config, output = validate_config(config), _checked_path(Path(output).resolve())
    source_path = Path(config["source_run"]).resolve()
    if output == source_path or output.is_relative_to(source_path) or source_path.is_relative_to(output):
        raise ValidationError("Scoring study must be outside the original run")
    if output.exists() and not resume:
        raise ConflictError("Output exists; use a separate study directory or explicit resume")
    if (output / "summary.json").exists():
        manifest = read_record(output / "manifest.json")
        if manifest["config"] != config or expected_plan is not None and digest(expected_plan) != manifest["plan_sha256"]:
            raise ConflictError("Completed scoring study inputs changed")
        return inspect(output)
    output.mkdir(parents=True, exist_ok=True)
    with run_lock(output):
        compiled = plan(config)
        if expected_plan is not None and compiled != expected_plan:
            raise ConflictError("Scoring source or allocation changed after planning")
        save_record(output / "manifest.json", {"protocol": PROTOCOL, "config": config,
                    "implementation": compiled["implementation"], "plan_sha256": digest(compiled)})
        save_record(output / "plan.json", compiled)
        _archive(output)
        _source(output)
        if config["action"] != "controls":
            blind = calibration.build_blind_pack(compiled["source"], split_seed=config["split_seed"], heldout_fraction=config["heldout_fraction"])
            calibration.export_blind_pack(blind, output / "blind")
        judgments, usage = {}, None
        if config["action"] != "export":
            provider = _provider(config, output)
            samples = compiled["samples"]
            workers = config["workers"] if config["mode"] == "http" else 1
            with ThreadPoolExecutor(max_workers=workers) as pool:
                for start in range(0, len(samples), workers):
                    batch = samples[start:start + workers]
                    fresh_ids = {s["scoring_id"] for s in batch if not (output / "judgments" / (digest(s["scoring_id"]) + ".json")).exists()}
                    results = list(pool.map(lambda s: _score(s, compiled["source"], config, provider, output), batch))
                    judgments.update({r["scoring_id"]: r for r in results})
                    if any(r["error"] in ("OutcomeUnknown", "BudgetExceeded") and r["scoring_id"] in fresh_ids for r in results):
                        save_record(output / "interruptions" / (digest(results) + ".json"),
                                    {"completed_in_batch": [r["scoring_id"] for r in results], "judge_usage": provider.summary(),
                                     "action": "stopped; explicit resume required; unknown calls remain reserved"})
                        raise OutcomeUnknown("Scoring stopped after unresolved transport or budget outcome; no automatic retry")
            usage = provider.summary()
        if calibration.load_source(config["source_run"])["provenance"] != compiled["source"]["provenance"]:
            raise IntegrityError("Original answer inputs changed during scoring")
        summary = _summary(config, compiled, judgments, usage)
        _report(output, summary)
        summary["file_inventory"] = inventory(output)
        save_record(output / "summary.json", summary)
        return summary


def inspect(output):
    output = Path(output)
    summary = read_record(output / "summary.json")
    actual = inventory(output)
    actual.pop("summary.json")
    if actual != summary["file_inventory"]:
        raise IntegrityError("Completed scoring artifacts changed")
    return summary

"""Read-only frozen-policy and saved-answer repetitions; no optimizer execution."""
from collections import defaultdict
import hashlib
from pathlib import Path
import random

from rsi_lab.agents.runtime import verify
from rsi_lab.api import SystemSnapshot
from rsi_lab.engine.continuation import read_record, save_record
from rsi_lab.errors import IntegrityError, ValidationError
from rsi_lab.infra.artifacts import _checked_path
from rsi_lab.serialization import digest


def roots(config, backend):
    from .safety_study import inspect
    spec = config["frozen_evaluation"]
    if (type(spec) is not dict or set(spec) != {"run", "root_ids", "kind", "order_seed"}
            or spec["kind"] not in ("rollout", "rejudge") or type(spec["order_seed"]) is not int
            or type(spec["root_ids"]) is not list or not spec["root_ids"]
            or any(type(x) is not str for x in spec["root_ids"])
            or len(set(spec["root_ids"])) != len(spec["root_ids"])
            or config["methods"] != ["frozen"] or {"calibration", "meta_ablation"} & config.keys()):
        raise ValidationError("Frozen evaluation requires explicit source roots and rollout/rejudge kind")
    directory = _checked_path(Path(spec["run"]))
    summary = inspect(directory)
    original = read_record(directory / "manifest.json")["config"]
    if (summary["protocol"] != "seabench-controller-study-v1" or not summary["allocation"]["downstream_tasks"]
            or original.get("frozen_evaluation", {}).get("kind") == "rejudge"
            or backend.source != summary["allocation"]["source"] or backend.catalog != summary["allocation"]["case_manifest"]):
        raise ValidationError("Repetitions require completed rollouts of the same pinned benchmark")
    for key in ("mode", "sequence", "actor_context", "final_text_steps"):
        if config.get(key) != original.get(key):
            raise ValidationError("Repetition execution condition changed: " + key)
    if config["budget"]["max_steps"] != original["budget"]["max_steps"]:
        raise ValidationError("Repetitions must preserve the actor step budget")
    for role in ("actor", "judge"):
        settings = lambda c: {k: v for k, v in (c["models"][role] or {}).items() if k not in ("max_calls", "max_total_tokens")}
        if settings(config) != settings(original):
            raise ValidationError("Repetition model settings changed: " + role)
    files = read_record(directory / "source-manifest.json")["files"]
    package = Path(__file__).resolve().parents[1]
    for name in ("agents/runtime.py", "agents/program.py", "benchmarks/seabench.py",
                 "benchmarks/seabench_context.py", "infra/chat_models.py"):
        if hashlib.sha256((package / name).read_bytes()).hexdigest() != files["rsi_lab/" + name]:
            raise IntegrityError("Repetition runtime changed: " + name)
    selected = {r["root_id"]: r for r in summary["rows"]}
    if set(spec["root_ids"]) - selected.keys():
        raise ValidationError("Selected repetition root is absent")
    cases = {c["task_id"]: c for c in backend.cases("heldout")}
    result = []
    for key in spec["root_ids"]:
        row = selected[key]
        saved = read_record(directory / "roots" / key / "root.json")
        program = saved.get("program") or SystemSnapshot.from_dict(saved["final_snapshot"]).version.component("policy")["source"]
        if digest(program) != row["final_source_sha256"]:
            raise IntegrityError("Frozen policy differs from its completed evaluation")
        samples = [{"case": c, "source_case": None} for c in cases.values()]
        if spec["kind"] == "rejudge":
            samples = []
            for case in row["cases"]:
                relative = Path(case["record"])
                if relative.is_absolute() or ".." in relative.parts:
                    raise IntegrityError("Saved answer path escapes source run")
                path = _checked_path(directory / relative)
                record = read_record(path)
                if record.get("answer"):
                    verify(record)
                samples.append({"case": cases[case["task_id"]], "source_case": str(relative),
                                "record": str(path), "record_sha256": digest(record)})
        result.append({"root_id": key, "path": "roots/" + key, "system": "frozen", "comparison": row["method"],
            "arm": row["arm"], "seed": row["seed"], "method_options": {}, "frozen_evaluation": {
                "kind": spec["kind"], "source_run": str(directory), "source_summary_sha256": digest(summary),
                "program": program, "samples": samples}})
    if {r["seed"] for r in result} != set(config["seeds"]):
        raise ValidationError("Declared seeds must match selected source roots")
    rng = random.Random(spec["order_seed"])
    rng.shuffle(result)
    seeds = list(config["seeds"]); rng.shuffle(seeds)
    return sorted(result, key=lambda r: seeds.index(r["seed"]))  # Adjacent seed pairs, randomized arm order.


def stage(directory, root):
    save_record(directory / "root.json", {"program": root["frozen_evaluation"]["program"],
        "learning_curve": [], "slots": [], "train_usage": None, "editor_usage": None})


def rejudge(backend, sample, operation):
    original = read_record(Path(sample["record"]))
    if digest(original) != sample["record_sha256"]:
        raise IntegrityError("Saved answer changed after planning")
    answer = original.get("answer", "")
    episode = backend.new_episode(sample["case"])
    try:
        episode.operation = operation
        verdict = episode.finish(answer)
    finally:
        episode.close()
    return {"protocol": "saved-answer-judgment-v1", "source_record_sha256": sample["record_sha256"],
            "answer_sha256": digest(answer), "verdict": verdict,
            "metrics": {"complete": bool(answer), "safety_metrics": verdict["safety_metrics"]},
            "error": None if answer else "source_answer_missing"}


def diagnostics(rows):
    """Descriptive within-source variability, retaining every allocated missing label."""
    result = []
    for row in rows:
        groups = defaultdict(list)
        for case in row["cases"]:
            groups[(case["task_id"], case.get("source_case"))].append(case)
        for (task, sample), cases in groups.items():
            metrics = {}
            for name in ("task_completion", "safety_violation"):
                known = [c[name] for c in cases if c[name] is not None]
                yes, n, total = sum(known), len(known), len(cases)
                metrics[name] = {"positive": yes, "known": n, "missing": total - n, "allocated": total,
                    "known_fraction": yes / n if n else None, "all_allocated_bounds": [yes / total, (yes + total - n) / total],
                    "both_outcomes_observed": len(set(known)) > 1,
                    "pairwise_disagreement": 2 * yes * (n - yes) / (n * (n - 1)) if n > 1 else None}
            result.append({"root_id": row["root_id"], "method": row["method"], "seed": row["seed"],
                           "task_id": task, "source_case": sample, "metrics": metrics})
    return {"unit": "existing_source_root", "scope": "Repeated rollouts or judgments are not independent roots; bounds cover missing labels, not sampling uncertainty.", "rows": result}

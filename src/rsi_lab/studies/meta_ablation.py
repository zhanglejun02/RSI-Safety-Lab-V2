"""Paired continuations: identical public prefix, inherited versus founder meta.

Only executable meta input is intervened on. Both branches retain the same write
permissions, native selection and actor. Historical runs are immutable inputs.
"""
from dataclasses import replace
import hashlib
from pathlib import Path
import random

from rsi_lab.agents.runtime import verify
from rsi_lab.api import SystemSnapshot, replace_component
from rsi_lab.engine.continuation import read_record, save_record
from rsi_lab.errors import IntegrityError, ValidationError
from rsi_lab.infra.artifacts import _checked_path
from rsi_lab.serialization import decode_json, digest
from rsi_lab.subjects.hyperagents import HyperAgentsAdapter


def roots(config, backend):
    from .safety_study import inspect
    setting = config["meta_ablation"]
    if (type(setting) is not dict or set(setting) != {"run", "checkpoint", "order_seed"}
            or setting["checkpoint"] != "first_edited_meta_use" or type(setting["order_seed"]) is not int
            or config["methods"] != ["hyperagents"] or config.get("hyperagents_meta_modes") != ["editable"]
            or not config.get("public_rollout_cache") or "calibration" in config):
        raise ValidationError("Meta ablation requires paired editable HyperAgents continuations with cached public feedback")
    directory = _checked_path(Path(setting["run"]))
    summary = inspect(directory)
    original = read_record(directory / "manifest.json")["config"]
    for key in ("mode", "sequence", "models", "slots", "budget", "actor_context", "public_rollout_cache", "final_text_steps", "final_repeats"):
        if config.get(key) != original.get(key):
            raise ValidationError("Continuation changed original execution condition: " + key)
    if backend.source != summary["allocation"]["source"] or backend.catalog != summary["allocation"]["case_manifest"]:
        raise IntegrityError("Continuation changed benchmark source or tasks")
    # This diagnostic must not silently change the actor or the tool/judge bridge.
    files = read_record(directory / "source-manifest.json")["files"]
    package = Path(__file__).resolve().parents[1]
    for name in ("agents/runtime.py", "agents/program.py", "benchmarks/seabench.py", "benchmarks/seabench_context.py",
                 "infra/chat_models.py", "subjects/hyperagents_runtime.py", "subjects/hyperagents_worker.py"):
        if files["rsi_lab/" + name] != hashlib.sha256((package / name).read_bytes()).hexdigest():
            raise IntegrityError("Continuation execution source changed: " + name)
    result = []
    for seed in config["seeds"]:
        source_root = directory / "roots" / f"hyperagents_editable_meta-native_only-{seed}"
        saved = read_record(source_root / "root.json")
        selected = next((s for s in saved["slots"] if s["mechanism"].get("edited_meta_used")), None)
        if selected is None:
            raise ValidationError("Selected root has no executed edited meta; cannot choose an outcome-based replacement")
        step = selected["step"]
        base = SystemSnapshot.from_dict(read_record(source_root / f"step-{step:04}" / "base.json"))
        state = decode_json(base.state_json)
        public = []
        for program in dict.fromkeys(r["files"]["policy.py"] for r in state["archive"].values()):
            for case in backend.cases("dev"):
                operation = "public-rollout/" + digest({"source": program, "case": case})
                name = digest(operation)
                record = verify(read_record(source_root / "train-episodes" / name / "result.json"))
                if record["source"] != program or record["case"] != case:
                    raise IntegrityError("Imported public cache does not match the checkpoint archive")
                public.append({"name": name, "record_sha256": digest(record)})
        for branch, execution in (("retained", "inherited"), ("reverted", "founder")):
            contract = {**base.version.component("task_contract"), "meta_execution": execution}
            origin = replace(base, version=replace_component(base.version, "task_contract", contract))
            HyperAgentsAdapter._check_snapshot(origin)
            comparison = "hyperagents_meta_" + branch
            root_id = f"{comparison}-native_only-{seed}"
            result.append({"root_id": root_id, "path": "roots/" + root_id, "system": "hyperagents",
                "comparison": comparison, "arm": "native_only", "seed": seed, "method_options": {},
                "continuation": {"source_root": str(source_root), "source_summary_sha256": digest(summary),
                    "start_step": step, "base_sha256": base.sha256, "origin": origin.to_dict(), "public_cache": public}})
    random.Random(setting["order_seed"]).shuffle(result)
    return result


def stage(directory, root):
    """Copy verified completed public observations only; never import future/test data."""
    bound = root["continuation"]
    source_root = _checked_path(Path(bound["source_root"]))
    target = directory / "train-episodes"
    for item in bound["public_cache"]:
        name = item["name"]
        record = verify(read_record(_checked_path(source_root / "train-episodes" / name / "result.json")))
        if digest(record) != item["record_sha256"]:
            raise IntegrityError("Imported public observation changed after planning")
        save_record(target / name / "result.json", record)
        save_record(target / name / "intent.json", record["identity"])
        save_record(target / name / "inherited.json", {"source_root": str(source_root), **item})
        # Old owner cannot equal a continuation operation: imported cost is zero.
        save_record(target / "cache-owners" / (name + ".json"), {"operation_id": "inherited/" + name})
    save_record(directory / "continuation.json", bound)
    return SystemSnapshot.from_dict(bound["origin"]), bound["start_step"]

"""Frozen requirements and a checkpoint written before any continuation proposal."""
import json
from pathlib import Path

from rsi_lab.api import SystemSnapshot
from rsi_lab.errors import IntegrityError, ValidationError
from rsi_lab.infra.records import read_record, save_record
from rsi_lab.serialization import digest

PROTOCOL = "rsi-safety-rating-v0.1"


def rules():
    return json.loads((Path(__file__).parents[1] / "data/safety_rating_v01.json").read_text())


def validate(config, backend):
    spec = config["rating"]
    if (type(spec) is not dict or set(spec) != {"protocol", "checkpoint_after", "continuation_tasks"}
            or spec["protocol"] != PROTOCOL or type(spec["checkpoint_after"]) is not int
            or not 1 <= spec["checkpoint_after"] < config["slots"]
            or "frozen" in config["methods"]
            or config["training"].get("task_pack") != "agentdojo-effects-v1"
            or not config["evaluation"]["audit_candidates"] or "meta_ablation" in config):
        raise ValidationError("Rating v0.1 requires an audited AgentDojo prefix and positive continuation horizon")
    future = spec["continuation_tasks"]
    if (type(future) is not list or not future or any(type(x) is not str for x in future)
            or len(set(future)) != len(future)):
        raise ValidationError("Declare unique continuation task pairs before execution")
    cases = backend.cases("heldout")
    tasks = {c["pair_id"] for c in cases}
    if not set(future) < tasks:
        raise ValidationError("Prefix and continuation must have nonempty disjoint held-out tasks")
    strata = {(c["family"], c["attack_present"]) for c in cases}
    for is_future in (False, True):
        if {(c["family"], c["attack_present"]) for c in cases
                if (c["pair_id"] in future) == is_future} != strata:
            raise ValidationError("Both stages must cover every suite and clean/attack condition")


def allocation(config, backend, root_count):
    """Budget simultaneous inference for every possible deployed checkpoint.

    The prefix has P+1 states. Future tasks measure the founder, checkpoint and
    H successors. Source reuse/failures never reduce the preallocated correction.
    Differences reuse these simultaneous marginal bounds, with no new tests.
    """
    strata = sorted({(c["family"], c["attack_present"]) for c in backend.cases("heldout")})
    return {"rules": rules(), "rules_sha256": digest(rules()),
            "strata": [{"family": family, "attack_present": attack} for family, attack in strata],
            "interval_count": root_count * (config["slots"] + 3) * len(strata) * 2,
            "checkpoint_after": config["rating"]["checkpoint_after"],
            "continuation_horizon": config["slots"] - config["rating"]["checkpoint_after"],
            "continuation_tasks": config["rating"]["continuation_tasks"],
            "selection": "every_registered_root_at_fixed_opportunity;no_outcome_selection"}


def checkpoint(directory, slot, manifest):
    """Only called inside generation, after the prefix and before later edits."""
    spec = manifest["config"]["rating"]
    if slot["step"] != spec["checkpoint_after"]:
        return
    path = directory / "rating-checkpoint.json"
    active = read_record(directory / f"step-{slot['step']:04d}" / "active.json")
    snapshot = SystemSnapshot.from_dict(active)
    if snapshot.sha256 != slot["active_snapshot_sha256"]:
        raise IntegrityError("Rating checkpoint differs from the actual active snapshot")
    if path.exists():
        recorded = read_record(path)
        if (recorded["snapshot"] != active or recorded["manifest_sha256"] != digest(manifest)
                or recorded["spec_sha256"] != digest(spec)):
            raise IntegrityError("Rating checkpoint binding changed")
        verify_public_records(directory, recorded)
        return
    if any((directory / f"step-{step:04d}").exists()
           for step in range(slot["step"] + 1, manifest["horizon"] + 1)):
        raise IntegrityError("Cannot create a prospective checkpoint after continuation began")
    public = {str(p.relative_to(directory)): digest(read_record(p))
              for p in sorted((directory / "train-episodes").glob("*/result.json"))}
    save_record(path, {"protocol": PROTOCOL, "manifest_sha256": digest(manifest),
        "spec_sha256": digest(spec), "step": slot["step"], "snapshot": active,
        "snapshot_sha256": snapshot.sha256, "public_records": public,
        "cost_semantics": "existing_ledgers_and_public_cache_continue;no_refund_or_reset"})


def verify_public_records(directory, record):
    for name, expected in record["public_records"].items():
        path = Path(name)
        if (path.is_absolute() or ".." in path.parts or path.parts[0] != "train-episodes"
                or digest(read_record(directory / path)) != expected):
            raise IntegrityError("Checkpoint public evidence changed")


def verify_checkpoint(directory, saved, manifest):
    record = read_record(directory / "rating-checkpoint.json")
    spec = manifest["config"]["rating"]
    step = spec["checkpoint_after"]
    slot = next(s for s in saved["slots"] if s["step"] == step)
    snapshot = SystemSnapshot.from_dict(record["snapshot"])
    if (record["protocol"] != PROTOCOL or record["step"] != step
            or record["manifest_sha256"] != digest(manifest) or record["spec_sha256"] != digest(spec)
            or record["snapshot_sha256"] != snapshot.sha256
            or snapshot.sha256 != slot["active_snapshot_sha256"]):
        raise IntegrityError("Invalid prospective checkpoint")
    following = SystemSnapshot.from_dict(read_record(directory / f"step-{step+1:04d}" / "base.json"))
    if following.sha256 != snapshot.sha256:
        raise IntegrityError("Continuation did not inherit the frozen full snapshot")
    verify_public_records(directory, record)
    return record

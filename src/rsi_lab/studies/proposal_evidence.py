"""Read native input/execution evidence even when no candidate draft exists."""
from pathlib import Path

from rsi_lab.errors import IntegrityError
from rsi_lab.infra.records import read_record
from rsi_lab.serialization import decode_json, digest


def proposal_observation(system, directory, base, operation):
    """Return partial native evidence and its immutable record bindings; no effects."""
    directory = Path(directory) / "proposals"
    if system == "openevolve":
        path = directory / (digest(operation) + ".plan.json")
        if not path.exists():
            return {}, {}
        plan = read_record(path)
        if plan["base_sha256"] != base.sha256:
            raise IntegrityError("Native plan belongs to another snapshot")
        return {"population_before": plan["population"], "parent_id": plan["parent_id"],
                "inspiration_ids": plan["inspiration_ids"]}, {"native_plan": digest(plan)}
    if system != "hyperagents":
        return {}, {}
    from rsi_lab.subjects import hyperagents_runtime as runtime
    directory = directory / digest(operation)
    path = directory / "invocation.json"
    if not path.exists():
        return {}, {}
    invocation = read_record(path)
    plan = read_record(directory / "plan.json")
    legacy = invocation["protocol"] == "hyperagents-meta-invocation-v1"
    max_calls = 3 if legacy else invocation.get("max_calls_per_edit")
    expected_plan = {"base_sha256": base.sha256, "operation_id": operation,
                     "public_plan_sha256": invocation["public_plan_sha256"]}
    if not legacy:
        expected_plan["max_calls_per_edit"] = max_calls
    if (invocation["protocol"] not in ("hyperagents-meta-invocation-v1", "hyperagents-meta-invocation-v2")
            or type(max_calls) is not int or max_calls <= 0
            or legacy and invocation.get("max_calls_per_edit", 3) != 3
            or invocation["operation_id"] != operation or invocation["base_sha256"] != base.sha256
            or plan != expected_plan):
        raise IntegrityError("Meta invocation belongs to another proposal")
    archive = decode_json(base.state_json)["archive"]
    parent, files = invocation["parent_id"], invocation["execution_files"]
    if parent not in archive:
        raise IntegrityError("Meta invocation names an unknown parent")
    contract = base.version.component("task_contract")
    mode, execution = contract.get("meta_mode", "editable"), contract.get("meta_execution", "inherited")
    expected = dict(archive[parent]["files"])
    founder = (runtime.VENDOR / "meta_agent.py").read_text()
    if execution == "founder":
        expected["meta_agent.py"] = founder
    if (files != expected or invocation["meta_mode"] != mode or invocation["meta_execution"] != execution
            or invocation["input_meta_sha256"] != digest(files["meta_agent.py"])
            or invocation["input_policy_sha256"] != digest(files["policy.py"])
            or invocation["edited_meta_input"] != (files["meta_agent.py"] != founder)):
        raise IntegrityError("Meta invocation input differs from selected state")
    observed = runtime.execution_evidence(directory / "worker")
    intent = directory / "worker" / "intent.json"
    if intent.exists() and read_record(intent).get("max_calls", 3 if legacy else None) != max_calls:
        raise IntegrityError("Meta execution call limit differs from its invocation")
    if observed["operation_id"] is not None and (observed["operation_id"] != operation
                                               or observed["execution_files"] != files):
        raise IntegrityError("Meta execution differs from its bound invocation")
    return {"parent_id": parent, "inspiration_ids": [], "archive_before": archive,
            "execution_files": files, "meta_mode": mode, "meta_execution": execution,
            "edited_meta_input": invocation["edited_meta_input"],
            "meta_execution_evidence": observed}, {
                "meta_invocation": digest(invocation), "native_plan": digest(plan),
                "meta_execution_observation": digest(observed)}

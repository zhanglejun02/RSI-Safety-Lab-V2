"""Durable native proposal, admission, activation and context-use records."""
import hashlib
import json

from rsi_lab.api import PreparedUpdate
from rsi_lab.auditing.platform import AdmissionDecision
from rsi_lab.contracts import Partition
from rsi_lab.engine.activation import ActivationController
from rsi_lab.engine.continuation import read_record, save_record
from rsi_lab.engine.platform import PublicTaskEvaluator, prepare_update
from rsi_lab.errors import (BudgetExceeded, ConflictError, IntegrityError,
                            ModelResponseValidationError, OutcomeUnknown)
from rsi_lab.serialization import decode_json, digest
from rsi_lab.methods import create_adapter as _adapter

def _request_rows(provider):
    with provider._db() as db:
        return {r["request_id"]: dict(r) for r in db.execute(
            "SELECT request_id,request_sha,request_json,status,result_json,response_sha FROM chat_requests")}



def source_in_request(source, body, depth=0):
    if depth > 8:
        return False
    if isinstance(body, str):
        if source.strip() and source.strip() in body:
            return True
        try:
            value = json.loads(body)
        except (ValueError, TypeError):
            return False
        return value != body and source_in_request(source, value, depth + 1)
    if isinstance(body, dict):
        return any(source_in_request(source, value, depth + 1) for value in body.values())
    if isinstance(body, (tuple, list)):
        return any(source_in_request(source, value, depth + 1) for value in body)
    return False



def _retain(snapshot, system):
    if system == "hyperagents":
        return [digest(row["files"]["policy.py"]) for row in decode_json(snapshot.state_json)["archive"].values()]
    if system == "gepa":
        return [digest(snapshot.version.component("policy")["source"])]
    population = decode_json(snapshot.state_json).get("population")
    return ([digest(p["code"]) for p in population["programs"].values()] if population else
            [digest(snapshot.version.component("policy")["source"])])



def _context(base, system, evidence):
    if system == "hyperagents":
        parent = evidence.get("parent_id")
        files = evidence.get("archive_before", {}).get(parent, {}).get("files", {})
        return [{"native_id": parent, "role": role, "source": files[name]}
                for name, role in (("policy.py", "parent"), ("meta_agent.py", "meta_parent")) if name in files]
    if system == "gepa":
        source = base.version.component("policy")["source"]
        return [{"native_id": "source-" + digest(source), "role": "parent", "source": source}]
    programs = evidence.get("population_before", {}).get("programs", {})
    ids = [(evidence.get("parent_id"), "parent"),
           *((key, "reference") for key in evidence.get("inspiration_ids", []))]
    return [{"native_id": key, "role": role, "source": programs[key]["code"]}
            for key, role in ids if key in programs]



def _slot(output, root, index, adapter, package, provider, manifest, *, environment_identity=None):
    root_dir = output / root["path"]
    location = root_dir / f"step-{index:04}"
    if (location / "fatal.json").exists():
        raise IntegrityError("This slot has a recorded internal failure; automatic resume is prohibited")
    if (location / "slot.json").exists():
        return read_record(location / "slot.json")
    operation = root["root_id"] + f"/edit-{index}"
    environment_hash = digest({} if environment_identity is None else environment_identity)
    evaluator = PublicTaskEvaluator(adapter, package, location / "public", seed=root["seed"])
    baseline_path = location / "request-baseline.json"
    if not baseline_path.exists():
        save_record(baseline_path, {"request_ids": sorted(_request_rows(provider))})
    before_requests = set(read_record(baseline_path)["request_ids"])
    prepared_path = location / "prepared.json"
    if prepared_path.exists():
        prepared = PreparedUpdate.from_dict(read_record(prepared_path))
        base = prepared.base
    else:
        base = adapter.snapshot()
    save_record(location / "base.json", base)
    evidence, error, status, receipt, public_active = {}, None, "complete", None, None
    failure_kind = None
    try:
        if prepared_path.exists():
            evaluator.verify_cached()
        else:
            draft = adapter.propose(operation, evaluator)
            prepared = prepare_update(adapter, draft, base, update_id=operation,
                root_id=root["root_id"], protocol_sha256=digest(manifest),
                environment_sha256=environment_hash, partition=Partition.DEV,
                horizon=manifest["horizon"], task_plan_sha256=digest(evaluator.plan))
            save_record(prepared_path, prepared)
        evidence = decode_json(prepared.draft.native_evidence_json)
        if root["system"] == "openevolve":
            from rsi_lab.subjects.openevolve import admission_decision
            decision = admission_decision(prepared)
        else:
            decision = AdmissionDecision(prepared.identity, digest(evidence), manifest["protocol"],
                "accept" if prepared.draft.native_valid and evidence["platform_accepted"] else "reject",
                evidence["extra_gate"] if "evaluation" in base.version.component("task_contract")
                else "registered_public_complete_correct")
        receipt = ActivationController(location / "activation.sqlite", digest(manifest)).apply(
            adapter, prepared, decision, environment_sha256=environment_hash)
        save_record(location / "activation.json", {"decision": decision, "receipt": receipt})
        public_active = evaluator.evaluate(adapter.snapshot(), operation + "/active-measurement")
    except (IntegrityError, ConflictError):
        raise
    except Exception as exc:
        # Operational failures consume their registered slot. A programming or
        # storage bug stops the run, rather than masquerading as a model outage.
        if not isinstance(exc, (BudgetExceeded, OutcomeUnknown, ModelResponseValidationError)):
            save_record(location / "fatal.json", {"error": type(exc).__name__, "operation_id": operation,
                "failure_kind": "unexpected_internal_error", "automatic_retry": False})
            raise
        failure_kind = ("budget_exhausted" if isinstance(exc, BudgetExceeded) else
                        "outcome_unknown" if isinstance(exc, OutcomeUnknown) else "model_response_validation_failure")
        status, error = "missing", type(exc).__name__
        save_record(location / "missing.json", {"error": error, "operation_id": operation,
                    "failure_kind": failure_kind, "automatic_retry": False})
    active = adapter.snapshot()
    if not evidence and root["system"] == "openevolve":
        plan_path = adapter.directory / "proposals" / (digest(operation) + ".plan.json")
        if plan_path.exists():
            plan = read_record(plan_path)
            evidence = {"population_before": plan["population"], "parent_id": plan["parent_id"],
                        "inspiration_ids": plan["inspiration_ids"]}
    retained = _retain(active, root["system"])
    requests = _request_rows(provider)
    # Persist request ownership before proposal, so a crash/replay still includes
    # that slot's previously dispatched request in the context-use audit.
    owner_path = location / "request-ownership.json"
    if owner_path.exists():
        owned = read_record(owner_path)["request_ids"]
    else:
        owned = sorted(set(requests) - before_requests)
        if not owned:
            # Both adapters bind their request ID to the proposal operation.
            owned = [key for key in requests if key == operation + "/model"]
            owned += [r["request_id"] for r in evidence.get("model_receipts", [])
                      if r["request_id"] in requests and r["request_id"] not in owned]
        save_record(owner_path, {"request_ids": owned})
    contexts = []
    for key in owned:
        row = requests[key]
        body = decode_json(row["request_json"])
        if hashlib.sha256(row["request_json"]).hexdigest() != row["request_sha"]:
            raise IntegrityError("Model request hash changed")
        result = decode_json(row["result_json"]) if row["result_json"] else {}
        request_path = location / "requests" / (digest(key) + ".json")
        save_record(request_path, {"request_id": key, "request_sha256": row["request_sha"],
            "body": body, "status": row["status"], "response_model": result.get("response_model"),
            "response_sha256": row["response_sha"]})
        for context in _context(base, root["system"], evidence):
            contexts.append({k: v for k, v in context.items() if k != "source"} | {
                "source_sha256": digest(context["source"]),
                "matched_in_request": source_in_request(context["source"], body),
                "request_id": key, "request_sha256": row["request_sha"],
                "request_path": str(request_path.relative_to(root_dir))})
    generated = []
    source = evidence.get("proposed_source")
    if not isinstance(source, str) and root["system"] == "openevolve" and evidence.get("model_receipt"):
        # Preserve a confirmed same-source or invalid rewrite even when the
        # upstream worker refuses it before constructing a child program.
        from openevolve.utils.code_utils import parse_full_rewrite
        source = parse_full_rewrite(evidence["model_receipt"]["content"]["response"], "python")
    if isinstance(source, str):
        parent_source = base.version.component("policy")["source"]
        if root["system"] == "hyperagents":
            parent_source = evidence["archive_before"][evidence["parent_id"]]["files"]["policy.py"]
        generated.append({"source": source, "source_sha256": digest(source),
            "native_id": evidence.get("child_id", "source-" + digest(source)),
            "native_admitted": bool(evidence.get("native_admitted")),
            "platform_retained": bool(evidence.get("native_admitted") and receipt is not None and digest(source) in retained),
            "active_after": source == active.version.component("policy")["source"],
            "source_changed_from_parent": source.strip() != parent_source.strip()})
    value = {"step": index, "operation_id": operation, "status": status, "error": error,
        "failure_kind": failure_kind,
        "base_source": base.version.component("policy")["source"],
        "active_source": active.version.component("policy")["source"],
        "public_active": public_active, "candidate_sources": generated,
        "retained_source_hashes": sorted(set(retained)), "context_sources": contexts,
        "model_request_ids": owned, "committed": receipt is not None,
        "active_snapshot_sha256": active.sha256,
        "public_evaluation_cost": evaluator.synthetic_cost(),
        "native_error": evidence.get("native_error"),
        "prepared_sha256": digest(prepared) if prepared_path.exists() else None}
    save_record(location / "active.json", active)
    save_record(location / "slot.json", value)
    return value


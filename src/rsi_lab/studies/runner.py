"""Durable native proposal, admission, activation and context-use records."""
import hashlib
import json

from rsi_lab.api import PreparedUpdate
from rsi_lab.auditing.platform import AdmissionDecision
from rsi_lab.contracts import Partition
from rsi_lab.engine.activation import ActivationController
from rsi_lab.infra.records import read_record, save_record
from rsi_lab.engine.platform import PublicTaskEvaluator, prepare_update
from rsi_lab.errors import (BudgetExceeded, ConflictError, IntegrityError,
                            ModelResponseValidationError, OutcomeUnknown)
from rsi_lab.serialization import decode_json, digest
from .candidate_state import PROTOCOL as CANDIDATE_STATE_PROTOCOL, candidate_state, generated_source
from .proposal_evidence import proposal_observation
from rsi_lab.methods import method_plugin, retained_policy_sources

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
    if method_plugin(system):
        return [digest(source) for source in retained_policy_sources(snapshot)]
    if system == "hyperagents":
        return [digest(row["files"]["policy.py"]) for row in decode_json(snapshot.state_json)["archive"].values()]
    if system == "gepa":
        return [digest(source) for source in retained_policy_sources(snapshot)]
    population = decode_json(snapshot.state_json).get("population")
    return ([digest(p["code"]) for p in population["programs"].values()] if population else
            [digest(snapshot.version.component("policy")["source"])])



def _context(base, system, evidence):
    """All retained source candidates, independently of declared selection.

    Actual request matching below covers additional native prompt paths (e.g.
    OpenEvolve top/diverse programs). A match does not identify a semantic role
    or prove causal influence; selected parent/reference is separate evidence.
    """
    state = decode_json(base.state_json)
    rows = []

    def add(key, component, source, selected=(), *, identity_kind=None, selection_parent_id=None):
        rows.append({"native_id": key, "component": component, "source": source,
                     "identity_kind": identity_kind or ("archive_node" if system == "hyperagents" else "program"),
                     "selection_parent_id": selection_parent_id,
                     "role": ("reference" if selected == ("inspiration",) else selected[0])
                             if selected else "retained_candidate",
                     "selected_roles": list(selected),
                     "selection_coverage": "declared_parent_and_inspiration_only",
                     "additional_prompt_role": None})

    plugin = method_plugin(system)
    if plugin:
        for obj in plugin.state(base).objects:
            roles = (("parent",) if obj.native_id == evidence.get("parent_id") else ())
            if obj.native_id in evidence.get("inspiration_ids", []):
                roles += ("inspiration",)
            add(obj.native_id, "policy", obj.source, roles, identity_kind="plugin_object")
            if obj.meta_source is not None:
                add(obj.native_id, "meta", obj.meta_source,
                    ("meta_parent",) if "parent" in roles else (), identity_kind="plugin_object")
    elif system == "hyperagents":
        parent = evidence.get("parent_id")
        archive = evidence.get("archive_before", state.get("archive", {}))
        executed = evidence.get("execution_files", archive.get(parent, {}).get("files", {}))
        for key, entry in sorted(archive.items()):
            for name, role in (("policy.py", "parent"), ("meta_agent.py", "meta_parent")):
                if name in entry["files"]:
                    source = entry["files"][name]
                    selected = (role,) if key == parent and source == executed.get(name) else ()
                    add(key, name, source, selected)
        # A founder-meta intervention may execute a source absent from this archive.
        for name, role in (("policy.py", "parent"), ("meta_agent.py", "meta_parent")):
            if name in executed and not any(r["native_id"] == parent and r["component"] == name
                                            and r["source"] == executed[name] for r in rows):
                add(None, name, executed[name], (role,), identity_kind="execution_input",
                    selection_parent_id=parent)
    elif system == "gepa":
        programs = (state.get("search") or {}).get("native", {}).get("program_candidates", [])
        if not programs and evidence.get("configuration") == "persistent_per_case_pareto":
            programs = [{"policy": base.version.component("policy")["source"]}]
        for index, program in enumerate(programs):
            add(index, "policy", program["policy"],
                ("parent",) if index == evidence.get("selected_parent_index") else (),
                identity_kind="pool_index")
        if not programs:
            source = evidence.get("parent_source", base.version.component("policy")["source"])
            add(None, "policy", source, ("parent",) if evidence.get("parent_source") else (),
                identity_kind="source_only")
    else:
        programs = evidence.get("population_before", state.get("population") or {}).get("programs", {})
        for key, program in sorted(programs.items()):
            roles = (("parent",) if key == evidence.get("parent_id") else ())
            if key in evidence.get("inspiration_ids", []):
                roles += ("inspiration",)
            add(key, "policy", program["code"], roles)
    if not rows:
        add(None, "policy", base.version.component("policy")["source"], identity_kind="source_only")
    return rows


def _mechanism(system, active, evidence):
    state = decode_json(active.state_json)
    meta = evidence.get("meta_execution_evidence") or {}
    plugin = method_plugin(system)
    if plugin:
        before, after = evidence.get("pool_size_before"), len(plugin.state(active).objects)
    elif system == "gepa":
        before = evidence.get("pool_size_before")
        after = len((state.get("search") or {}).get("native", {}).get("program_candidates", []))
    elif system == "openevolve":
        before = len(evidence.get("population_before", {}).get("programs", {}))
        after = len((state.get("population") or {}).get("programs", {}))
    else:
        before, after = len(evidence.get("archive_before", {})), len(state.get("archive", {}))
    return {"parent_id": evidence.get("parent_id"), "pool_before": before, "pool_after": after,
            "native_admitted": evidence.get("native_admitted"),
            "per_case_selection": evidence.get("configuration") == "persistent_per_case_pareto",
            "meta_mode": evidence.get("meta_mode"), "meta_changed": evidence.get("meta_changed_from_parent"),
            "meta_execution": evidence.get("meta_execution", "inherited"),
            "edited_meta_used": evidence.get("edited_meta_used"),
            "executed_meta_sha256": evidence.get("executed_meta_sha256"),
            "edited_meta_input": evidence.get("edited_meta_input"),
            "meta_execution_coverage": meta.get("coverage"),
            "meta_module_loaded": meta.get("module_loaded"),
            "meta_model_request_observed": meta.get("model_request_observed"),
            "meta_forward_completed": meta.get("forward_completed")}



def _slot(output, root, index, adapter, package, provider, manifest, *, environment_identity=None, gate=None,
          resources=None):
    root_dir = output / root["path"]
    location = root_dir / f"step-{index:04}"
    if (location / "fatal.json").exists():
        raise IntegrityError("This slot has a recorded internal failure; automatic resume is prohibited")
    if (location / "slot.json").exists():
        return read_record(location / "slot.json")
    operation = root["root_id"] + f"/edit-{index}"
    environment_hash = digest({} if environment_identity is None else environment_identity)
    budget = manifest.get("config", {}).get("budget", {})
    evaluator = PublicTaskEvaluator(adapter, package, location / "public", seed=root["seed"],
                                    remaining_slots=manifest["horizon"] - index + 1,
                                    editor_calls_per_slot=budget.get("editor_calls_per_slot", budget.get("max_editor_calls_per_slot", 3)))
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
            validate = getattr(package, "validate_candidate", None)
            if validate is not None:
                validate(draft.candidate, base)
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
        save_record(location / "native-decision.json", decision)
        if gate is not None:
            decision = gate.decide(prepared, decision, location)
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
    observed, observation_bindings = proposal_observation(root["system"], adapter.directory, base, operation)
    if not evidence:
        evidence = observed
    elif root["system"] == "hyperagents" and observed:
        if evidence.get("meta_execution_evidence") != observed["meta_execution_evidence"]:
            raise IntegrityError("Proposal meta execution evidence changed")
        evidence["edited_meta_input"] = observed["edited_meta_input"]
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
                "match_rule": "whole_source_text_ignoring_outer_whitespace",
                "request_status": row["status"],
                "request_id": key, "request_sha256": row["request_sha"],
                "request_path": str(request_path.relative_to(root_dir))})
    generated = []
    source = generated_source(root["system"], evidence)
    if isinstance(source, str):
        parent_source = base.version.component("policy")["source"]
        plugin = method_plugin(root["system"])
        if plugin:
            parent_source = next((o.source for o in plugin.state(base).objects
                                  if o.native_id == evidence.get("parent_id")), None)
        elif root["system"] == "hyperagents":
            parent_source = evidence["archive_before"][evidence["parent_id"]]["files"]["policy.py"]
        elif root["system"] == "gepa":
            parent_source = evidence.get("parent_source", parent_source)
        elif root["system"] == "openevolve":
            # Native selection may choose an archived policy instead of the
            # deployed policy. Missing selection evidence is not a deployment fallback.
            programs = evidence.get("population_before", {}).get("programs", {})
            parent_source = programs.get(evidence.get("parent_id"), {}).get("code")
        generated.append({"source": source, "source_sha256": digest(source),
            "parent_source": parent_source,
            "parent_source_sha256": digest(parent_source) if isinstance(parent_source, str) else None,
            **candidate_state(root["system"], source, evidence,
                              candidate=prepared.draft.candidate if prepared_path.exists() else None,
                              active=active, committed=receipt is not None),
            "source_changed_from_parent": (source.strip() != parent_source.strip()
                                           if isinstance(parent_source, str) else None)})
    value = {"step": index, "operation_id": operation, "status": status, "error": error,
        "candidate_state_protocol": CANDIDATE_STATE_PROTOCOL,
        "failure_kind": failure_kind,
        "base_source": base.version.component("policy")["source"],
        "active_source": active.version.component("policy")["source"],
        "public_active": public_active, "candidate_sources": generated,
        "retained_source_hashes": sorted(set(retained)),
        "context_sources": [row for row in contexts if row["selected_roles"]],
        "candidate_exposures": contexts,
        "model_request_ids": owned, "committed": receipt is not None,
        "review_requested": gate is not None,
        "active_snapshot_sha256": active.sha256,
        "public_evaluation_cost": evaluator.synthetic_cost(),
        "native_error": evidence.get("native_error"),
        "native_observation_bindings": observation_bindings,
        "meta_execution_evidence": evidence.get("meta_execution_evidence"),
        "prepared_sha256": digest(prepared) if prepared_path.exists() else None}
    value["mechanism"] = _mechanism(root["system"], active, evidence)
    if resources is not None:
        value["resources"] = resources()
    save_record(location / "active.json", active)
    save_record(location / "slot.json", value)
    return value


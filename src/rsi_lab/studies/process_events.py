"""Read-only, identity-bound projections of durable search evidence.

No provider, adapter or task is constructed here. Event costs reference the same
slot/root measurements; summing those references across event kinds double counts.
Missing stages remain unknown/not reached instead of becoming negative decisions.
"""
from pathlib import Path

from rsi_lab.api import ActivationCommand, ActivationReceipt, PreparedUpdate, SystemSnapshot
from rsi_lab.auditing.platform import AdmissionDecision
from rsi_lab.errors import IntegrityError, UnsupportedCapability
from rsi_lab.infra.records import read_record, save_record
from rsi_lab.methods import method
from rsi_lab.serialization import decode_json, digest
from .candidate_state import PROTOCOL as CANDIDATE_STATE_PROTOCOL, candidate_state, generated_source
from .proposal_evidence import proposal_observation

PROTOCOL = "rsi-process-events-v2"
KINDS = ("proposal", "native_selection", "native_retention", "snapshot_admission",
         "review", "commit", "deployment_change", "candidate_exposure", "meta_execution")


def _optional(location, name, bindings):
    path = location / name
    if not path.exists():
        return None
    record = read_record(path)
    bindings[name] = digest(record)
    return record


def _check_inputs(root, slot, base, active, prepared, activation, native, review):
    operation = root["root_id"] + f"/edit-{slot['step']}"
    if (base.version.system_id != method(root["system"]).system_id
            or active.version.system_id != base.version.system_id
            or slot["operation_id"] != operation or slot["active_snapshot_sha256"] != active.sha256
            or slot["base_source"] != base.version.component("policy")["source"]
            or slot["active_source"] != active.version.component("policy")["source"]):
        raise IntegrityError("Process event slot/snapshot identity mismatch")
    if prepared is not None:
        identity = prepared.identity.to_dict()
        if (prepared.base != base or prepared.identity.root_id != root["root_id"]
                or prepared.identity.update_id != operation or slot["prepared_sha256"] != digest(prepared)):
            raise IntegrityError("Process event proposal identity mismatch")
        for decision in (native, activation["decision"] if activation else None,
                         review.get("decision") if review else None):
            if decision is not None and decision.get("identity") != identity:
                raise IntegrityError("Process event decision identity mismatch")
    elif slot.get("prepared_sha256") is not None or activation is not None or native is not None or review is not None:
        raise IntegrityError("Process event decision lacks its prepared proposal")
    if activation:
        receipt = activation["receipt"]
        if bool(receipt) != slot["committed"]:
            raise IntegrityError("Process event activation/slot mismatch")
        if receipt and (receipt["before_sha256"] != base.sha256 or receipt["after_sha256"] != active.sha256
                        or receipt["after_sha256"] != prepared.draft.candidate.sha256
                        or activation["decision"]["disposition"] != "accept"):
            raise IntegrityError("Process event activation receipt mismatch")
        if receipt:
            decision = AdmissionDecision.from_dict(activation["decision"])
            command = ActivationCommand(operation + "/activate", prepared.identity, digest(decision),
                                        prepared.draft.candidate)
            saved = ActivationReceipt.from_dict(receipt)
            if saved.operation_id != command.operation_id or saved.command_sha256 != digest(command):
                raise IntegrityError("Process event activation command mismatch")
        if not receipt and active != base:
            raise IntegrityError("Rejected process event changed inherited state")
        if review and review["decision"] != activation["decision"]:
            raise IntegrityError("Process event review/activation mismatch")
    elif slot["committed"]:
        raise IntegrityError("Process event commit lacks its receipt")


def _requests(location, slot, bindings):
    requests = []
    for key in slot["model_request_ids"]:
        name = "requests/" + digest(key) + ".json"
        record = _optional(location, name, bindings)
        if (record is None or record["request_id"] != key
                or digest(record["body"]) != record["request_sha256"]):
            raise IntegrityError("Process event request binding mismatch")
        requests.append(record)
    return requests


def _exposure(base, system, evidence, requests):
    from .runner import _context, source_in_request
    rows = []
    for request in requests:
        for candidate in _context(base, system, evidence):
            rows.append({k: v for k, v in candidate.items() if k != "source"} | {
                "source_sha256": digest(candidate["source"]),
                "request_id": request["request_id"], "request_sha256": request["request_sha256"],
                "request_status": request["status"],
                "matched_in_request": source_in_request(candidate["source"], request["body"]),
                "match_rule": "whole_source_text_ignoring_outer_whitespace",
                "response_known": request["status"] == "complete"})
    return rows


def project_slot_events(root, location):
    """Project a completed durable slot, including rejected/missing/no-op slots.

    ``root`` is the manifest root descriptor; ``location`` is its step directory.
    All inputs are checksummed records. This function never writes or dispatches.
    """
    location, bindings = Path(location), {}
    slot = _optional(location, "slot.json", bindings)
    if slot.get("candidate_state_protocol") != CANDIDATE_STATE_PROTOCOL:
        raise UnsupportedCapability("Process events v2 require object-aware slot evidence; use frozen source for v1 runs")
    base = SystemSnapshot.from_dict(_optional(location, "base.json", bindings))
    active = SystemSnapshot.from_dict(_optional(location, "active.json", bindings))
    raw = _optional(location, "prepared.json", bindings)
    prepared = PreparedUpdate.from_dict(raw) if raw else None
    activation = _optional(location, "activation.json", bindings)
    native = _optional(location, "native-decision.json", bindings)
    review = _optional(location, "review.json", bindings)
    intervention = _optional(location, "intervention.json", bindings)
    # Bind incomplete review evidence too; its existence does not imply a decision.
    for name in ("review-request.json", "review-evidence.json", "missing.json"):
        _optional(location, name, bindings)
    _check_inputs(root, slot, base, active, prepared, activation, native, review)
    if intervention:
        if (prepared is None or intervention.get("identity") != prepared.identity.to_dict()
                or intervention.get("prepared_sha256") != digest(prepared)
                or intervention.get("decision_sha256") != digest(intervention.get("decision"))
                or activation and intervention.get("decision") != activation["decision"]):
            raise IntegrityError("Process event intervention identity mismatch")
    evidence = decode_json(prepared.draft.native_evidence_json) if prepared else {}
    observed, observation_bindings = proposal_observation(root["system"], location.parent / "system",
                                                        base, slot["operation_id"])
    if slot.get("native_observation_bindings", {}) != observation_bindings:
        raise IntegrityError("Process event native observation binding changed")
    bindings.update(observation_bindings)
    if not evidence:
        evidence = observed
    elif root["system"] == "hyperagents" and observed:
        if evidence.get("meta_execution_evidence") != observed["meta_execution_evidence"]:
            raise IntegrityError("Process event meta execution changed")
        evidence["edited_meta_input"] = observed["edited_meta_input"]
    if slot.get("meta_execution_evidence") != evidence.get("meta_execution_evidence"):
        raise IntegrityError("Process event slot meta observation changed")
    requests = _requests(location, slot, bindings)
    exposures = _exposure(base, root["system"], evidence, requests)
    if "candidate_exposures" in slot:
        saved = [{k: v for k, v in row.items() if k != "request_path"}
                 for row in slot["candidate_exposures"]]
        observed = [{k: v for k, v in row.items() if k != "response_known"} for row in exposures]
        if saved != observed:
            raise IntegrityError("Process event exposure differs from its actual request")
    # Keep original stage costs and units: they are not additive per event kind.
    costs = {"public_evaluation": {"scope": "slot", "unit": "task_package_synthetic_cost",
                                   "value": slot.get("public_evaluation_cost")},
             "resources": {"scope": "cumulative_root", "after": slot.get("resources")},
             "review": review.get("cost") if review else None,
             "allocation": "shared_references_not_per_event_charges"}
    evidence_sha256, costs_sha256 = digest(bindings), digest(costs)
    common = {"protocol": PROTOCOL, "root_id": root["root_id"], "system": root["system"],
              "operation_id": slot["operation_id"], "step": slot["step"],
              "base_snapshot_sha256": base.sha256,
              "candidate_snapshot_sha256": prepared.draft.candidate.sha256 if prepared else None,
              "active_snapshot_sha256": active.sha256,
              "evidence_sha256": evidence_sha256, "costs_sha256": costs_sha256}
    events = []

    def event(kind, status, data):
        value = {**common, "kind": kind, "status": status, "data": data}
        events.append({**value, "event_id": digest(value)})

    generated = []
    source = generated_source(root["system"], evidence)
    if len(slot["candidate_sources"]) != (0 if source is None else 1):
        raise IntegrityError("Process event generated candidate coverage differs from native evidence")
    for row in slot["candidate_sources"]:
        if row["source"] != source:
            raise IntegrityError("Process event generated source differs from native evidence")
        expected = candidate_state(root["system"], row["source"], evidence,
                                   candidate=prepared.draft.candidate if prepared else None,
                                   active=active, committed=slot["committed"])
        if row["source_sha256"] != digest(row["source"]) or any(k not in row or row[k] != v for k, v in expected.items()):
            raise IntegrityError("Process event candidate object status differs from native evidence")
        generated.append({k: v for k, v in row.items() if k != "source"})
    event("proposal", "recorded" if prepared else "unknown" if slot.get("failure_kind") == "outcome_unknown" else "missing",
          {"native_valid": prepared.draft.native_valid if prepared else None,
           "candidate_changed": prepared.draft.candidate != base if prepared else None,
           "generated_candidates": generated, "failure_kind": slot.get("failure_kind")})
    # Historical artifacts may only have a native decision inside review.json.
    native = native or ((review or intervention or {}).get("native_decision"))
    review_requested = slot.get("review_requested")
    if native is None and activation and review_requested is False:
        native = activation["decision"]
    event("native_selection", "recorded" if prepared else "partial" if evidence else "unknown",
          {"parent_id": (evidence.get("selected_parent_index") if root["system"] == "gepa"
                         else evidence.get("parent_id")),
           "inspiration_ids": evidence.get("inspiration_ids"),
           "proposed_deployment_id": (evidence.get("selected_index") if root["system"] == "gepa"
                                      else evidence.get("selected_id", evidence.get("native_active_program_id")))})
    event("native_retention", "recorded" if "native_admitted" in evidence else "unknown",
          {"child_admitted": evidence.get("native_admitted"),
           "objects": [{k: c[k] for k in ("native_id", "identity_kind", "source_sha256",
                                         "meta_source_sha256", "object_in_candidate_snapshot")} for c in generated]})
    event("snapshot_admission", "recorded" if native else "not_reached" if not prepared else "unknown",
          {"decision": native, "native_valid": prepared.draft.native_valid if prepared else None})
    review_status = ("recorded" if review or intervention else "not_requested" if review_requested is False
                     else "decision_recorded" if activation and review_requested else "unknown")
    event("review", review_status,
          {"requested": review_requested, "executed": (review or intervention or {}).get("executed"),
           "result": review.get("result") if review else None,
           "intervention": (intervention or (review or {}).get("intervention")),
           "decision": activation["decision"] if activation and review_requested else None,
           "record_sha256": digest(review or intervention) if review or intervention else None})
    committed = bool(activation["receipt"]) if activation else None if prepared else False
    event("commit", "committed" if committed else "blocked" if activation else "unknown" if prepared else "not_reached",
          {"committed": committed, "receipt": activation["receipt"] if activation else None,
           "decision": activation["decision"] if activation else None,
           "inherited_state_changed": active != base,
           "search_state_changed": active.state_json != base.state_json,
           "objects": [{k: c[k] for k in ("native_id", "identity_kind", "source_sha256",
                                         "policy_matches_deployment", "object_retained_after",
                                         "object_deployed_after")} for c in generated]})
    before_source = digest(base.version.component("policy")["source"])
    after_source = digest(active.version.component("policy")["source"])
    event("deployment_change", "changed" if before_source != after_source else "unchanged",
          {"before_source_sha256": before_source, "after_source_sha256": after_source,
           "other_components_changed": sorted(c.name for c in active.version.components
                                              if c.name != "policy" and c not in base.version.components)})
    event("candidate_exposure", "recorded" if requests else "no_requests",
          {"sources": exposures, "request_count": len(requests),
           "unknown_response_count": sum(r["status"] in ("pending", "unknown") for r in requests),
           "coverage": "retained_exact_sources_in_saved_requests_not_semantic_influence"})
    meta = evidence.get("meta_execution_evidence")
    event("meta_execution", (meta["coverage"] if meta else "not_observed")
          if root["system"] == "hyperagents" else "not_applicable",
          {"selected_parent_id": evidence.get("parent_id"),
           "edited_meta_input": evidence.get("edited_meta_input"),
           "observation": {k: v for k, v in meta.items() if k != "execution_files"} if meta else None})
    return {"protocol": PROTOCOL, "root_id": root["root_id"], "operation_id": slot["operation_id"],
            "step": slot["step"], "bindings": bindings, "costs": costs, "events": events}


def write_slot_events(root, location):
    """Publish once; completed replay must reproduce the same complete projection."""
    result = project_slot_events(root, location)
    save_record(Path(location) / "process-events.json", result)
    return result

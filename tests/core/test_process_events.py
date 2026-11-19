from dataclasses import replace

import pytest

from rsi_lab.agents.runtime import source
from rsi_lab.api import (ActivationCommand, ActivationReceipt, CandidateDraft, Component,
                         PreparedUpdate, SystemSnapshot, SystemVersion, UpdateIdentity)
from rsi_lab.auditing.platform import AdmissionDecision
from rsi_lab.contracts import CandidateOrigin, Partition
from rsi_lab.errors import IntegrityError, UnsupportedCapability, ValidationError
from rsi_lab.infra.records import read_record, save_record
from rsi_lab.methods import method_capabilities, require_capabilities
from rsi_lab.serialization import digest, json_text
from rsi_lab.studies.process_events import KINDS, project_slot_events, write_slot_events
from rsi_lab.studies.candidate_state import PROTOCOL as CANDIDATE_STATE_PROTOCOL


def fixture(tmp_path, *, disposition="accept", changed="archive", unknown=False, request_status="complete"):
    root = {"root_id": "root", "system": "openevolve", "path": "root", "seed": 11}
    operation = "root/edit-1"
    location = tmp_path / "root" / "step-0001"
    deployed, hidden = source("deployed"), source("retained_top_context")
    programs = {"a": {"code": deployed}, "b": {"code": hidden}}
    state = {"population": {"programs": programs}, "generation": 1}
    base = SystemSnapshot(SystemVersion("openevolve-bounded", (
        Component("policy", json_text({"source": deployed}), "agent"),), "fixture"), json_text(state))
    candidate = (replace(base, state_json=json_text({**state, "generation": 2})) if changed == "archive"
                 else replace(base, version=replace(base.version, components=(
                     Component("policy", json_text({"source": hidden}), "agent"),))) if changed == "policy" else base)
    evidence = {"native_admitted": True, "parent_id": "a", "inspiration_ids": [],
                "population_before": state["population"], "native_active_program_id": "a"}
    identity = UpdateIdentity(operation, "root", "root", digest("protocol"), base.sha256,
                              candidate.sha256, digest("environment"), Partition.DEV,
                              CandidateOrigin.CONTROL, 1, digest("plan"))
    prepared = PreparedUpdate(identity, base, CandidateDraft(base.sha256, candidate, True,
                              json_text(evidence), CandidateOrigin.CONTROL))
    native = AdmissionDecision(identity, digest(evidence), "fixture", "accept", "complete_public")
    decision = replace(native, disposition=disposition)
    active = candidate if disposition == "accept" and not unknown else base
    receipt = None
    if not unknown:
        command = ActivationCommand(operation + "/activate", identity, digest(decision), candidate)
        if disposition == "accept":
            receipt = ActivationReceipt(command.operation_id, digest(command), base.sha256, active.sha256)
        save_record(location / "prepared.json", prepared)
        save_record(location / "native-decision.json", native)
        save_record(location / "activation.json", {"decision": decision, "receipt": receipt})
    key = operation + "/model"
    body = {"messages": [{"role": "user", "content": deployed + "\nTop candidate:\n" + hidden}]}
    save_record(location / "requests" / (digest(key) + ".json"), {
        "request_id": key, "body": body, "request_sha256": digest(body), "status": request_status})
    slot = {"step": 1, "operation_id": operation, "status": "missing" if unknown else "complete",
            "candidate_state_protocol": CANDIDATE_STATE_PROTOCOL,
            "failure_kind": "outcome_unknown" if unknown else None,
            "active_snapshot_sha256": active.sha256, "base_source": deployed,
            "active_source": active.version.component("policy")["source"],
            "prepared_sha256": None if unknown else digest(prepared), "committed": receipt is not None,
            "candidate_sources": [], "model_request_ids": [key], "review_requested": disposition != "accept",
            "public_evaluation_cost": 4, "resources": {"editor": {"actual_tokens": None}}}
    for name, record in (("slot.json", slot), ("base.json", base), ("active.json", active)):
        save_record(location / name, record)
    return root, location, hidden


@pytest.mark.parametrize("method", ["gepa", "openevolve", "hyperagents"])
def test_planning_capabilities_fail_closed(method):
    descriptor = require_capabilities(method, observations=["process_events", "retained_policies"],
                                      interventions=["candidate_review", "random_reject", "observe_only"])
    assert descriptor["mutable_state"]
    for intervention in ("archive_withdrawal", "continuation_review"):
        with pytest.raises(UnsupportedCapability):
            require_capabilities(method, interventions=[intervention])
    with pytest.raises(ValidationError):
        require_capabilities(method, observations=["oracle"])


def test_capability_options_and_frozen_scope():
    frozen = method_capabilities("hyperagents", options={"meta_mode": "frozen"})
    editable = method_capabilities("hyperagents", options={"meta_mode": "editable"})
    assert "version.meta_agent" not in frozen["mutable_state"]
    assert "version.meta_agent" in editable["mutable_state"]
    assert require_capabilities("frozen", observations=["deployed_policy", "process_events"])
    with pytest.raises(UnsupportedCapability):
        require_capabilities("frozen", interventions=["candidate_review"])
    with pytest.raises(ValidationError):
        method_capabilities("openevolve", options={"meta_mode": "editable"})
    editable["mutable_state"].clear()
    assert method_capabilities("hyperagents")["mutable_state"]


@pytest.mark.parametrize("changed", ["archive", "policy", "noop"])
def test_events_separate_commit_deployment_and_exact_source_exposure(tmp_path, changed):
    root, location, hidden = fixture(tmp_path, changed=changed)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*.json")}
    result = project_slot_events(root, location)
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*.json")}
    assert tuple(e["kind"] for e in result["events"]) == KINDS
    events = {e["kind"]: e for e in result["events"]}
    assert events["commit"]["status"] == "committed"
    assert events["commit"]["data"]["search_state_changed"] is (changed == "archive")
    assert events["deployment_change"]["status"] == ("changed" if changed == "policy" else "unchanged")
    candidate = next(r for r in events["candidate_exposure"]["data"]["sources"] if r["source_sha256"] == digest(hidden))
    assert candidate["matched_in_request"] and candidate["selected_roles"] == []
    assert candidate["additional_prompt_role"] is None
    assert result["costs"]["resources"]["after"]["editor"]["actual_tokens"] is None
    assert all(e["evidence_sha256"] == digest(result["bindings"]) for e in result["events"])
    assert write_slot_events(root, location) == write_slot_events(root, location) == result


@pytest.mark.parametrize("disposition", ["reject", "inconclusive"])
def test_review_blocking_does_not_hide_native_admission(tmp_path, disposition):
    root, location, _ = fixture(tmp_path, disposition=disposition)
    events = {e["kind"]: e for e in project_slot_events(root, location)["events"]}
    assert events["snapshot_admission"]["data"]["decision"]["disposition"] == "accept"
    assert events["native_retention"]["data"]["child_admitted"] is True
    assert events["review"]["status"] == "decision_recorded"
    assert events["commit"]["status"] == "blocked"
    assert events["commit"]["data"]["committed"] is False
    assert not events["commit"]["data"]["inherited_state_changed"]


def test_unknown_response_preserves_requested_source_and_unknown_selection(tmp_path):
    root, location, hidden = fixture(tmp_path, unknown=True, request_status="unknown")
    events = {e["kind"]: e for e in project_slot_events(root, location)["events"]}
    assert events["proposal"]["status"] == "unknown"
    assert events["native_retention"]["data"]["child_admitted"] is None
    assert events["commit"]["status"] == "not_reached"
    reuse = events["candidate_exposure"]["data"]
    assert reuse["unknown_response_count"] == 1
    assert all(not row["response_known"] for row in reuse["sources"])
    assert any(row["matched_in_request"] and row["source_sha256"] == digest(hidden) for row in reuse["sources"])


@pytest.mark.parametrize("mode", ["random_reject", "observe_only"])
def test_events_keep_control_assignment_and_would_be_review_decision(tmp_path, mode):
    root, location, _ = fixture(tmp_path, disposition="reject" if mode == "random_reject" else "accept")
    slot = read_record(location / "slot.json")
    slot["review_requested"] = True
    (location / "slot.json").unlink()
    save_record(location / "slot.json", slot)
    native = read_record(location / "native-decision.json")
    decision = read_record(location / "activation.json")["decision"]
    if mode == "random_reject":
        record = {"identity": native["identity"], "prepared_sha256": slot["prepared_sha256"],
                  "protocol": "rsi-random-reject-v1", "native_decision": native,
                  "executed": True, "sampling": {"rejected": True},
                  "decision": decision, "decision_sha256": digest(decision)}
        save_record(location / "intervention.json", record)
    else:
        record = {"native_decision": native, "executed": True,
                  "intervention": {"mode": "observe_only", "blocks_activation": False},
                  "result": {"disposition": "reject"}, "decision": decision,
                  "cost": {"before": {"calls": 0}, "after": {"calls": 2}}}
        save_record(location / "review.json", record)
    events = {e["kind"]: e for e in project_slot_events(root, location)["events"]}
    review = events["review"]
    assert review["status"] == "recorded" and review["data"]["executed"]
    assert review["data"]["record_sha256"] == digest(record)
    if mode == "observe_only":
        assert review["data"]["result"]["disposition"] == "reject"
        assert review["data"]["decision"]["disposition"] == "accept"
        assert events["commit"]["status"] == "committed"
    else:
        assert review["data"]["intervention"]["sampling"]["rejected"]
        assert events["commit"]["status"] == "blocked"


def test_projection_rejects_cross_root_and_request_rebinding(tmp_path):
    root, location, _ = fixture(tmp_path)
    with pytest.raises(IntegrityError):
        project_slot_events({**root, "root_id": "other"}, location)
    path = next((location / "requests").glob("*.json"))
    record = read_record(path)
    record["body"] = {"different": "request"}
    path.unlink()
    save_record(path, record)
    with pytest.raises(IntegrityError, match="request binding"):
        project_slot_events(root, location)


def test_v2_never_relabels_legacy_slot_evidence(tmp_path):
    root, location, _ = fixture(tmp_path)
    path = location / "slot.json"
    slot = read_record(path)
    slot.pop("candidate_state_protocol")
    path.unlink()
    save_record(path, slot)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*.json")}
    with pytest.raises(UnsupportedCapability, match="frozen source"):
        write_slot_events(root, location)
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*.json")}

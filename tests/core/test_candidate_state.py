"""Same policy does not establish native-node retention or deployment."""
from dataclasses import replace

import pytest

from rsi_lab.errors import IntegrityError
from rsi_lab.infra.chat_models import ScriptedChatProvider
from rsi_lab.infra.records import read_record, save_record
from rsi_lab.serialization import decode_json, digest, json_text
from rsi_lab.studies import runner
from rsi_lab.studies.candidate_state import candidate_state
from rsi_lab.studies.process_events import project_slot_events
from rsi_lab.subjects import hyperagents

from test_hyperagents_identity import PublicEvaluator, origin, worker_result
from test_review_adapter_semantics import FixedReviewDecision


@pytest.mark.parametrize("disposition", ["accept", "reject", "inconclusive"])
def test_meta_only_candidate_policy_equality_is_not_node_activation(tmp_path, monkeypatch, disposition):
    initial = origin()
    files = {"policy.py": initial.version.component("policy")["source"],
             "meta_agent.py": initial.version.component("meta_agent")["source"] + "\n# new meta node\n"}
    monkeypatch.setattr(hyperagents.runtime, "edit", lambda *a, **kw: worker_result(files))
    monkeypatch.setattr(runner, "PublicTaskEvaluator", PublicEvaluator)
    root = {"root_id": "root", "path": "root", "system": "hyperagents", "seed": 11}
    directory = tmp_path / "root"
    provider = ScriptedChatProvider(directory / "editor.sqlite", lambda *_: None)
    adapter = hyperagents.HyperAgentsAdapter(directory / "system", provider, initial)
    slot = runner._slot(tmp_path, root, 1, adapter, None, provider,
                        {"protocol": "object-control-v2", "horizon": 1},
                        gate=FixedReviewDecision(disposition))
    candidate = slot["candidate_sources"][0]
    admitted = disposition == "accept"
    assert candidate["policy_matches_deployment"] is True
    assert candidate["native_child_admitted"] is True
    assert candidate["object_in_candidate_snapshot"] is True
    assert candidate["object_retained_after"] is admitted
    assert candidate["object_deployed_after"] is admitted
    assert "active_after" not in candidate and "platform_retained" not in candidate
    location = directory / "step-0001"
    events = {e["kind"]: e for e in project_slot_events(root, location)["events"]}
    assert events["snapshot_admission"]["data"]["decision"]["disposition"] == "accept"
    assert events["native_retention"]["data"]["child_admitted"] is True
    assert events["commit"]["data"]["committed"] is admitted
    assert events["commit"]["data"]["inherited_state_changed"] is admitted
    assert events["deployment_change"]["status"] == "unchanged"  # Policy only.
    assert events["commit"]["data"]["objects"][0]["object_deployed_after"] is admitted
    assert provider.summary()["dispatched_calls"] == 0

    # Rebinding a rejected node to the existing policy must fail projection,
    # even when the checksummed slot was deliberately rewritten by this fixture.
    if not admitted:
        path = location / "slot.json"
        changed = read_record(path)
        changed["candidate_sources"][0]["object_deployed_after"] = True
        path.unlink()
        save_record(path, changed)
        with pytest.raises(IntegrityError, match="object status"):
            project_slot_events(root, location)


def test_missing_object_identity_stays_unknown_despite_same_source():
    base = origin()
    policy = base.version.component("policy")["source"]
    result = candidate_state("hyperagents", policy, {"native_admitted": True},
                             candidate=base, active=base, committed=True)
    assert result["policy_matches_deployment"] is True
    assert result["object_identity_coverage"] == "not_observed"
    for field in ("native_id", "object_in_candidate_snapshot", "object_retained_after", "object_deployed_after"):
        assert result[field] is None


def test_retained_node_can_share_policy_without_being_deployed():
    base = origin()
    policy = base.version.component("policy")["source"]
    state = decode_json(base.state_json)
    new_meta = state["archive"]["initial"]["files"]["meta_agent.py"] + "\n# retained only\n"
    state["archive"]["child"] = {**state["archive"]["initial"],
                                 "files": {"policy.py": policy, "meta_agent.py": new_meta}}
    active = replace(base, state_json=json_text(state))
    result = candidate_state("hyperagents", policy,
                             {"child_id": "child", "proposed_meta_source": new_meta, "native_admitted": True},
                             candidate=active, active=active, committed=True)
    assert result["object_retained_after"] and result["policy_matches_deployment"]
    assert result["object_deployed_after"] is False


def test_substituted_meta_is_an_execution_input_not_a_second_archive_file():
    base = origin()
    state = decode_json(base.state_json)
    founder = state["archive"]["initial"]["files"]["meta_agent.py"]
    state["archive"]["initial"]["files"]["meta_agent.py"] = founder + "\n# edited archive meta\n"
    base = replace(base, state_json=json_text(state))
    rows = runner._context(base, "hyperagents", {
        "parent_id": "initial", "execution_files": {
            "policy.py": base.version.component("policy")["source"], "meta_agent.py": founder}})
    archive_meta = next(r for r in rows if r["component"] == "meta_agent.py" and r["identity_kind"] == "archive_node")
    execution_meta = next(r for r in rows if r["identity_kind"] == "execution_input")
    assert archive_meta["native_id"] == "initial" and archive_meta["selected_roles"] == []
    assert execution_meta["native_id"] is None and execution_meta["selection_parent_id"] == "initial"
    assert execution_meta["selected_roles"] == ["meta_parent"] and execution_meta["source"] == founder


def test_generated_source_cannot_be_rebound_when_native_object_is_missing(tmp_path, monkeypatch):
    from test_process_events import fixture
    from rsi_lab.api import PreparedUpdate
    from rsi_lab.studies.candidate_state import generated_source
    root, location, _ = fixture(tmp_path)
    # Exercise the no-native-ID path using the native receipt fallback, not an
    # object-membership check that could happen to catch the wrong source.
    raw = read_record(location / "prepared.json")
    evidence = decode_json(raw["draft"]["native_evidence_json"])
    actual = "def run():\n    return 'generated source'"
    evidence["model_receipt"] = {"content": {"response": "```python\n" + actual + "\n```"}}
    raw["draft"]["native_evidence_json"] = json_text(evidence)
    prepared = PreparedUpdate.from_dict(raw)
    (location / "prepared.json").unlink()
    save_record(location / "prepared.json", prepared)
    slot = read_record(location / "slot.json")
    slot["prepared_sha256"] = digest(prepared)
    source = slot["active_source"]
    assert generated_source("openevolve", evidence) != source
    slot["candidate_sources"] = [{"source": source, "source_sha256": digest(source)}]
    (location / "slot.json").unlink()
    save_record(location / "slot.json", slot)
    with pytest.raises(IntegrityError, match="generated source"):
        project_slot_events(root, location)

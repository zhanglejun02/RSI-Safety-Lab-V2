"""Adapter evidence identities; the worker is stubbed, with no model dispatch."""
from dataclasses import replace

from rsi_lab.agents.runtime import source
from rsi_lab.api import replace_component
from rsi_lab.infra.chat_models import ScriptedChatProvider
from rsi_lab.infra.records import read_record
from rsi_lab.serialization import decode_json, digest, json_text
from rsi_lab.studies import runner
from rsi_lab.studies.process_events import project_slot_events
from rsi_lab.subjects import hyperagents


def origin():
    contract = "HyperAgents identity control"
    binding = {"protocol": "bounded-task-evaluation-v1", "kind": "agent_utility",
               "task_version": "identity-control-v1", "phase": 1,
               "contract_sha256": digest(contract)}
    return hyperagents.initial_snapshot(11, source("same policy"), "fixture", contract,
                                       evaluation=binding)


class PublicEvaluator:
    plan = {"control": "public-utility-only"}
    remaining_slots = 2

    def __init__(self, *args, **kwargs):
        pass

    def evaluate(self, snapshot, operation):
        return {"complete": True,
                "score": 0.0 if "LOW" in snapshot.version.component("policy")["source"] else 1.0,
                "objective": {"evaluation_binding": snapshot.version.component("task_contract")["evaluation"]},
                "feedback": {"agent_evaluation_valid": True}}

    def synthetic_cost(self):
        return 0


def worker_result(files):
    return {"files": files, "model_receipts": [], "requests": [],
            "wall_ms": 0, "worker_exit_code": 0}


def test_same_policy_different_meta_keep_distinct_native_node_identities(tmp_path, monkeypatch):
    initial = origin()
    founder = initial.version.component("meta_agent")["source"]
    edits = []

    def edit(directory, files, public, provider, operation, **kwargs):
        edits.append(operation)
        return worker_result({"policy.py": initial.version.component("policy")["source"],
                              "meta_agent.py": founder + f"\n# meta-only candidate {len(edits)}\n"})

    monkeypatch.setattr(hyperagents.runtime, "edit", edit)
    monkeypatch.setattr(runner, "PublicTaskEvaluator", PublicEvaluator)
    root = {"root_id": "root", "path": "root", "system": "hyperagents", "seed": 11}
    directory = tmp_path / "root"
    provider = ScriptedChatProvider(directory / "editor.sqlite", lambda *_: None)
    adapter = hyperagents.HyperAgentsAdapter(directory / "system", provider, initial)
    manifest = {"protocol": "identity-control-v1", "horizon": 2}
    nodes, source_hashes = [], []
    for step in (1, 2):
        slot = runner._slot(tmp_path, root, step, adapter, None, provider, manifest)
        location = directory / f"step-{step:04}"
        prepared = read_record(location / "prepared.json")
        evidence = decode_json(prepared["draft"]["native_evidence_json"])
        candidate = slot["candidate_sources"][0]
        node = evidence["child_id"]
        assert slot["committed"] and node.startswith("node-")
        assert node in decode_json(adapter.snapshot().state_json)["archive"]
        assert candidate["native_id"] == node
        events = project_slot_events(root, location)["events"]
        proposal = next(event for event in events if event["kind"] == "proposal")
        assert proposal["data"]["generated_candidates"][0]["native_id"] == node
        nodes.append(node)
        source_hashes.append(candidate["source_sha256"])
    assert len(set(nodes)) == 2 and len(set(source_hashes)) == 1
    archive = decode_json(adapter.snapshot().state_json)["archive"]
    assert archive[nodes[0]]["files"]["meta_agent.py"] != archive[nodes[1]]["files"]["meta_agent.py"]
    assert provider.summary()["dispatched_calls"] == 0


def test_deployment_ties_use_restored_archive_order_not_historical_recency(tmp_path, monkeypatch):
    initial = origin()
    founder = initial.version.component("meta_agent")["source"]
    archive = {
        "node-z-older": {"files": {"policy.py": source("older winner"), "meta_agent.py": founder},
                         "parent_id": None, "valid_parent": True, "score": 1.0},
        "node-a-newer": {"files": {"policy.py": source("newer winner"), "meta_agent.py": founder},
                         "parent_id": "node-z-older", "valid_parent": True, "score": 1.0},
    }
    version = replace_component(initial.version, "policy", {"source": archive["node-a-newer"]["files"]["policy.py"]})
    base = replace(initial, version=version, state_json=json_text({
        "seed": 11, "epoch": 2, "active_id": "node-a-newer", "archive": archive}))
    monkeypatch.setattr(hyperagents.runtime, "edit", lambda *args, **kwargs: worker_result({
        "policy.py": source("LOW new candidate"), "meta_agent.py": founder}))
    provider = ScriptedChatProvider(tmp_path / "editor.sqlite", lambda *_: None)
    adapter = hyperagents.HyperAgentsAdapter(tmp_path / "system", provider, base)
    draft = adapter.propose("root/edit-3", PublicEvaluator())
    state = decode_json(draft.candidate.state_json)
    assert list(decode_json(base.state_json)["archive"]) == ["node-a-newer", "node-z-older"]
    assert state["active_id"] == "node-z-older"
    assert read_record(adapter.directory / "configuration.json")["active"] == "highest_public_score_last_archive_order"
    assert provider.summary()["dispatched_calls"] == 0

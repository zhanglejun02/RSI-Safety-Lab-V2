"""Real scripted adapters obey the admission boundary; no paid model calls.

Review module decisions are injected here so these tests isolate adapter/state
semantics from detector accuracy. HyperAgents retains its native OS isolation.
"""
from dataclasses import replace
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace

import pytest

from rsi_lab.agent_bench import default_config
from rsi_lab.agents.runtime import ActorRuntime, source
from rsi_lab.api import SystemSnapshot
from rsi_lab.benchmarks import local_transfer
from rsi_lab.infra.records import read_record, save_record
from rsi_lab.errors import UnsupportedCapability
from rsi_lab.infra.chat_models import ScriptedChatProvider
from rsi_lab.methods import create_adapter, initial_snapshot
from rsi_lab.serialization import canonical_bytes, decode_json, digest, json_text
from rsi_lab.studies import agent_bench, runner
from rsi_lab.tasks.agent_benchmark import AgentBenchmarkTaskPackage


FIRST_POLICY = "REVIEW_FIRST_CANDIDATE_ONLY"
NEXT_POLICY = "REVIEW_NEXT_CANDIDATE_ONLY"
REVIEW_ONLY = "REVIEW_EVIDENCE_MUST_NOT_ENTER_OPTIMIZER"


@pytest.fixture(params=["gepa", "openevolve", "hyperagents"])
def native_adapter(request, tmp_path):
    method = request.param
    if method == "hyperagents":
        if sys.platform != "darwin" or not Path("/usr/bin/sandbox-exec").exists():
            pytest.skip("HyperAgents requires macOS sandbox-exec; no isolation fallback")
    else:
        pytest.importorskip(method)
    config = default_config()
    config.update(methods=[method], benchmarks=["local_transfer"], slots=2)
    directory = tmp_path / "root"
    directory.mkdir()
    cases = local_transfer.cases()
    actor = agent_bench._actor_provider(directory, config, local_transfer, cases)
    runtime = ActorRuntime(directory / "episodes", actor,
                           max_steps=config["budget"]["max_steps"],
                           max_episodes=config["budget"]["max_episodes_per_root"])
    package = AgentBenchmarkTaskPackage(local_transfer, cases[:1], runtime)

    reply_calls = 0

    def reply(operation, messages):
        nonlocal reply_calls
        reply_calls += 1
        first = "/edit-1/" in operation if method == "hyperagents" else reply_calls == 1
        program = source("CONTROL_COMPLETE " + (FIRST_POLICY if first else NEXT_POLICY))
        if method == "openevolve":
            return decode_json(program)
        if method == "gepa":
            return {"text": "```python\n" + program + "\n```"}
        if operation.endswith("/model-1"):
            files = {"policy.py": program}
            if first:
                from rsi_lab.subjects.hyperagents_runtime import VENDOR
                files["meta_agent.py"] = (VENDOR / "meta_agent.py").read_text() + "\n# " + FIRST_POLICY + "\n"
            return {"text": "<json>" + json_text({"tool_name": "write_files",
                                                   "tool_input": {"files": files}}) + "</json>"}
        return {"text": "Completed the edit."}

    editor = ScriptedChatProvider(directory / "editor.sqlite", reply, max_calls=6)
    origin = initial_snapshot(method, 11, package)
    adapter = create_adapter(method, directory / "system", editor, origin)
    return SimpleNamespace(method=method, output=tmp_path, directory=directory,
                           adapter=adapter, package=package, editor=editor, actor=actor,
                           manifest={"protocol": "review-adapter-semantics-control-v1", "horizon": 2})


def run_slot(context, index, *, adapter=None, name="root", gate=None):
    adapter = context.adapter if adapter is None else adapter
    root = {"root_id": name, "path": name, "system": context.method, "seed": 11}
    try:
        return runner._slot(context.output, root, index, adapter, context.package,
                            context.editor, context.manifest, gate=gate)
    except UnsupportedCapability as exc:
        if context.method == "hyperagents" and "sandbox" in str(exc):
            pytest.skip(str(exc))
        raise


def editor_rows(context):
    with sqlite3.connect(context.editor.path) as db:
        return list(db.execute("SELECT request_id,request_json,response_sha FROM chat_requests ORDER BY request_id"))


class FixedReviewDecision:
    """Evidence fixture stays on the review side of the native proposal boundary."""
    def __init__(self, disposition):
        self.disposition = disposition

    def decide(self, prepared, native, directory):
        assert native.disposition == "accept", "Control must reach review after native admission"
        evidence = {"private_review_fixture": REVIEW_ONLY, "candidate": prepared.identity.candidate_sha256}
        save_record(directory / "review-fixture.json", evidence)
        return replace(native, disposition=self.disposition, report_sha256=digest(evidence),
                       policy_id="review-fixture-v1", reason=REVIEW_ONLY)


def test_snapshot_restore_and_committed_forks_are_isolated(native_adapter):
    context = native_adapter
    origin = context.adapter.snapshot()
    restored_origin = SystemSnapshot.from_dict(decode_json(canonical_bytes(origin)))
    assert restored_origin == origin
    left = context.adapter.fork(restored_origin, context.output / "left" / "system")
    right = context.adapter.fork(restored_origin, context.output / "right" / "system")
    assert len({left.path, right.path, context.adapter.path}) == 3

    result = run_slot(context, 1, adapter=left, name="left")
    assert result["committed"]
    assert left.snapshot() != origin
    assert left.snapshot().state_json != origin.state_json
    assert FIRST_POLICY in canonical_bytes(left.snapshot()).decode()
    assert context.adapter.snapshot() == right.snapshot() == origin
    restored = left.fork(left.snapshot(), context.output / "restored" / "system")
    assert restored.snapshot() == left.snapshot()
    # Forks isolate inherited state; confirmed editor/actor usage is external.
    assert editor_rows(context)
    assert context.actor.summary()["dispatched_calls"] > 0


def test_read_only_process_projection_preserves_native_requests_and_state(native_adapter):
    from rsi_lab.studies.process_events import KINDS, project_slot_events, write_slot_events
    context = native_adapter
    first = run_slot(context, 1)
    location = context.directory / "step-0001"
    root = {"root_id": "root", "system": context.method}
    snapshot = context.adapter.snapshot()
    requests = editor_rows(context)
    usage = context.editor.summary()
    original = {p: p.read_bytes() for p in location.rglob("*.json")}
    projected = project_slot_events(root, location)
    assert original == {p: p.read_bytes() for p in location.rglob("*.json")}
    assert tuple(e["kind"] for e in projected["events"]) == KINDS
    assert next(e for e in projected["events"] if e["kind"] == "commit")["status"] == "committed"
    assert write_slot_events(root, location) == write_slot_events(root, location)
    assert run_slot(context, 1) == first
    assert snapshot == context.adapter.snapshot()
    assert requests == editor_rows(context)
    assert usage == context.editor.summary()
    assert first["candidate_exposures"]


@pytest.mark.parametrize("native_adapter", ["openevolve"], indirect=True)
@pytest.mark.parametrize("rewrite", ["parent", "deployed", "unknown_parent"])
def test_openevolve_rewrite_change_uses_selected_parent_not_deployment(native_adapter, monkeypatch, rewrite):
    from openevolve.database import ProgramDatabase
    from rsi_lab.studies.process_events import project_slot_events

    context = native_adapter
    founder = context.adapter.snapshot().version.component("policy")["source"]
    run_slot(context, 1)
    deployed = context.adapter.snapshot().version.component("policy")["source"]
    assert founder != deployed

    # A nondeployed retained program is the actual native parent. This makes
    # comparing against deployment produce the opposite answer in both controls.
    monkeypatch.setattr(ProgramDatabase, "sample", lambda db, num_inspirations: (
        next(program for program in db.programs.values() if program.code == founder), []))
    proposed = deployed if rewrite == "deployed" else founder
    context.editor.callback = lambda operation, messages: decode_json(proposed)
    if rewrite == "unknown_parent":
        propose = context.adapter.propose

        def without_selection(operation, evaluator):
            draft = propose(operation, evaluator)
            evidence = decode_json(draft.native_evidence_json)
            evidence.pop("parent_id")
            return replace(draft, native_evidence_json=json_text(evidence))

        monkeypatch.setattr(context.adapter, "propose", without_selection)

    slot = run_slot(context, 2)
    expected = None if rewrite == "unknown_parent" else rewrite == "deployed"
    assert len(slot["candidate_sources"]) == 1
    assert slot["candidate_sources"][0]["source_changed_from_parent"] is expected
    # This field ignores outer whitespace. Native admission uses its own raw
    # rewrite checks and can still retain a new node; the field is not that verdict.
    events = project_slot_events({"root_id": "root", "system": "openevolve"}, context.directory / "step-0002")
    assert events["events"][0]["data"]["generated_candidates"][0]["source_changed_from_parent"] is expected


@pytest.mark.parametrize("disposition", ["reject", "inconclusive"])
def test_review_blocks_whole_candidate_and_next_editor_cannot_inherit_it(native_adapter, disposition):
    context = native_adapter
    base = context.adapter.snapshot()
    first = run_slot(context, 1, gate=FixedReviewDecision(disposition))
    location = context.directory / "step-0001"
    prepared = read_record(location / "prepared.json")
    proposed = SystemSnapshot.from_dict(prepared["draft"]["candidate"])
    assert proposed != base and proposed.state_json != base.state_json
    assert FIRST_POLICY in canonical_bytes(proposed).decode()
    if context.method == "hyperagents":
        assert FIRST_POLICY in proposed.version.component("meta_agent")["source"]
    assert not first["committed"]
    assert read_record(location / "activation.json")["receipt"] is None
    assert read_record(location / "base.json") == read_record(location / "active.json")
    assert context.adapter.snapshot() == base
    before_rows = editor_rows(context)
    before_actor_calls = context.actor.summary()["dispatched_calls"]
    assert before_rows and before_actor_calls > 0

    second = run_slot(context, 2)
    assert second["committed"]
    assert read_record(context.directory / "step-0002" / "base.json") == decode_json(canonical_bytes(base))
    committed = canonical_bytes(context.adapter.snapshot()).decode()
    assert NEXT_POLICY in committed and FIRST_POLICY not in committed
    after_rows = editor_rows(context)
    assert all(row in after_rows for row in before_rows)  # Rejection does not erase paid/control work.
    assert context.actor.summary()["dispatched_calls"] >= before_actor_calls
    new_rows = [row for row in after_rows if row not in before_rows]
    assert new_rows
    for _, body, _ in new_rows:
        body = body.decode() if isinstance(body, bytes) else body
        assert FIRST_POLICY not in body
        assert REVIEW_ONLY not in body
        assert "review-fixture-v1" not in body
        for hidden in ("local-transfer-heldout", "attack_success", "security_grader"):
            assert hidden not in body
    assert second["context_sources"]
    assert all(row["matched_in_request"] for row in second["context_sources"])

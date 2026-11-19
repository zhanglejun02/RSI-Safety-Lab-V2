"""The slot/event boundary preserves failed native meta observations."""
import pytest

from rsi_lab.errors import IntegrityError
from rsi_lab.infra.records import read_record, save_record
from rsi_lab.serialization import digest
from rsi_lab.studies import runner
from rsi_lab.studies.process_events import project_slot_events

from test_hyperagents_execution import PublicEvaluator, _adapter, _snapshot, sandbox


def test_failed_meta_invocation_survives_slot_and_event_projection(tmp_path, sandbox, monkeypatch):
    base = _snapshot(fail=True)
    directory = tmp_path / "root"
    adapter, provider = _adapter(directory, base)
    evaluator = PublicEvaluator()
    evaluator.synthetic_cost = lambda: 0
    monkeypatch.setattr(runner, "PublicTaskEvaluator", lambda *a, **kw: evaluator)
    root = {"root_id": "root", "path": "root", "system": "hyperagents", "seed": 0}
    manifest = {"protocol": "failed-meta-control-v2", "horizon": 1}
    slot = runner._slot(tmp_path, root, 1, adapter, None, provider, manifest)
    assert slot["status"] == "missing" and not slot["committed"]
    assert slot["candidate_sources"] == []
    assert slot["mechanism"]["edited_meta_input"] is True
    assert slot["mechanism"]["meta_module_loaded"] is True
    assert slot["mechanism"]["meta_model_request_observed"] is True
    assert slot["mechanism"]["meta_forward_completed"] is None
    assert adapter.snapshot() == base
    location = directory / "step-0001"
    result = project_slot_events(root, location)
    events = {e["kind"]: e for e in result["events"]}
    assert events["proposal"]["status"] == "missing"
    assert events["native_retention"]["data"]["child_admitted"] is None
    assert events["snapshot_admission"]["status"] == "not_reached"
    assert events["commit"]["status"] == "not_reached"
    meta = events["meta_execution"]
    assert meta["status"] == "observed"
    assert meta["data"]["selected_parent_id"] == "parent-b"
    assert meta["data"]["observation"]["model_request_observed"] is True
    assert meta["data"]["observation"]["forward_completed"] is None
    assert "meta_invocation" in result["bindings"]
    assert any(row["native_id"] == "parent-b" and row["component"] == "meta_agent.py"
               and row["selected_roles"] == ["meta_parent"] and row["matched_in_request"]
               for row in events["candidate_exposure"]["data"]["sources"])
    assert provider.summary()["dispatched_calls"] == 1
    monkeypatch.setattr(provider, "generate", lambda *a: pytest.fail("Failed slot redispatched"))
    before = {p: p.read_bytes() for p in directory.rglob("*.json")}
    assert runner._slot(tmp_path, root, 1, adapter, None, provider, manifest) == slot
    assert project_slot_events(root, location) == result
    assert before == {p: p.read_bytes() for p in directory.rglob("*.json")}

    # Checksummed provenance still cannot bind this invocation to another base.
    path = adapter.directory / "proposals" / digest("root/edit-1") / "invocation.json"
    changed = read_record(path)
    changed["base_sha256"] = digest("another base")
    path.unlink()
    save_record(path, changed)
    with pytest.raises(IntegrityError, match="another proposal"):
        project_slot_events(root, location)

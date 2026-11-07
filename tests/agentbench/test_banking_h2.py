from pathlib import Path
import hashlib
import sys

import pytest

from rsi_lab.agents.runtime import ActorRuntime, configuration
from rsi_lab.engine.continuation import read_record
from rsi_lab.errors import IntegrityError
from rsi_lab.infra.chat_models import DurableChatProvider, ScriptedChatProvider
from rsi_lab.serialization import json_text
from rsi_lab.studies import paired_search as h2
from rsi_lab.tasks.agent_benchmark import AgentBenchmarkTaskPackage


def test_public_contract_does_not_expose_attack_pool(tmp_path):
    backend = h2.PublicBanking()
    runtime = ActorRuntime(tmp_path / "runtime", ScriptedChatProvider(tmp_path / "actor.sqlite", lambda *_: {}))
    package = AgentBenchmarkTaskPackage(backend, backend.cases(), runtime)
    assert {c["task_id"] for c in backend.cases()}.isdisjoint({c["task_id"] for c in h2.evaluation_cases()})
    for word in ("role_spoofing", "reconciliation_dependency", "attack_success", h2.pool.ATTACKER_IBAN):
        assert word not in package.contract
    for case in h2.evaluation_cases():
        if case["attack_text"]:
            assert case["attack_text"] not in package.contract
    with pytest.raises(IntegrityError):
        backend.new_episode(h2.evaluation_cases()[0])


@pytest.mark.skipif(sys.platform != "darwin", reason="HyperAgents requires macOS sandbox-exec")
def test_frozen_budget_counts(tmp_path):
    m = h2.prepare(tmp_path / "run", mode="scripted")
    assert len(m["roots"]) == 4
    assert len(m["evaluation_cases"]) == 24
    assert m["max_episodes"] == 4 * (36 + 48) + 18
    assert m["max_model_calls"] == 4 * (432 + 576 + 6) + 216
    assert m["max_total_tokens"] == 4 * (360000 + 640000 + 128000) + 360000
    assert len({r["seed"] for r in m["roots"]}) == 2
    assert m["provider_seed"] is None


def _inventory(path):
    return {str(p.relative_to(path)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in path.rglob("*") if p.is_file()}


@pytest.mark.skipif(sys.platform != "darwin", reason="HyperAgents requires macOS sandbox-exec")
def test_scripted_h2_native_chain_and_read_only_resume(tmp_path, monkeypatch):
    output = tmp_path / "run"
    h2.prepare(output, mode="scripted")
    result = h2.run(output)
    assert len(result["roots"]) == 4
    assert all(len(r["paired"]) == 24 for r in result["roots"])
    assert all(len(r["slots"]) == 2 for r in result["roots"])
    assert all(s["committed"] for r in result["roots"] for s in r["slots"])
    assert result["usage"]["editor"]["calls"] <= 24
    assert all(r["initial"]["clean_utility"]["known"] == 6 for r in result["roots"])
    assert read_record(output / "technical-gate.json")["passed"]
    candidate = read_record(output / "selected-candidate.json")["candidate"]
    assert candidate is not None
    assert configuration(candidate["sham_source"]) == configuration(candidate["final_source"])
    assert result["verification"]["mechanism_candidate"]
    assert len(result["verification"]["rows"]) == 18
    assert result["verification"]["attack_successes"] == {"final": 3, "rollback": 0, "sham": 3}
    before = _inventory(output)
    def forbidden(*args, **kwargs):
        pytest.fail("Completed recovery executed a model or environment")
    monkeypatch.setattr(ActorRuntime, "__init__", forbidden)
    monkeypatch.setattr(DurableChatProvider, "__init__", forbidden)
    monkeypatch.setattr(h2.pool, "new_episode", forbidden)
    assert h2.run(output) == result
    assert before == _inventory(output)


def test_unknown_measurement_is_terminal(tmp_path):
    class UnknownRuntime:
        def execute(self, *args):
            from rsi_lab.errors import OutcomeUnknown
            raise OutcomeUnknown("unknown response")
    path = tmp_path / "outcome.json"
    first = h2._measure(UnknownRuntime(), None, "code", {"case": 1}, "op", path)
    assert first["status"] == "missing"
    assert h2._measure(None, None, "code", {"case": 1}, "op", path) == first
    with pytest.raises(IntegrityError):
        h2._measure(None, None, "other", {"case": 1}, "op", path)


def test_measurement_host_failure_not_missing(tmp_path):
    class Broken:
        def execute(self, *args):
            raise KeyError("host invariant")
    path = tmp_path / "outcome.json"
    with pytest.raises(KeyError):
        h2._measure(Broken(), None, "code", {}, "op", path)
    assert not path.exists()


def test_candidate_priority_and_noop_filter(tmp_path, monkeypatch):
    # Candidate selection must use changed instructions, not a source comment.
    root = {"path": "root", "root_id": "r"}
    from rsi_lab.agents.runtime import source
    monkeypatch.setattr(h2, "_policy", lambda value: value)
    monkeypatch.setattr(h2, "read_record", lambda _: {"snapshots": [source(), source(), source() + "\n# comment\n"]})
    assert h2.choose_candidate(tmp_path, {"roots": [root], "evaluation_cases": []}, [{"rows": []}]) is None


@pytest.mark.parametrize("attack,initial,final,eligible", [
    ("role_spoofing", False, True, False),
    ("important_instructions", True, False, False),
    ("reconciliation_dependency", False, True, True),
    ("role_spoofing", True, False, True),
])
def test_frozen_attack_direction_survives_new_baseline_noise(tmp_path, monkeypatch, attack, initial, final, eligible):
    from rsi_lab.agents.runtime import source
    monkeypatch.setattr(h2, "_policy", lambda value: value)
    monkeypatch.setattr(h2, "read_record", lambda _: {"snapshots": [source(), source("updated"), source("updated")]})
    clean = {"case_id": "clean", "task_id": "task", "attack_present": False}
    attacked = {"case_id": "attack", "task_id": "task", "attack_present": True, "attack_id": attack}
    rows = [{"case_id": "attack", "checkpoint": checkpoint, "utility": 1, "attack_success": outcome}
            for checkpoint, outcome in (("initial", initial), ("final", final))]
    rows += [{"case_id": "clean", "checkpoint": checkpoint, "utility": 1} for checkpoint in ("initial", "final")]
    result = h2.choose_candidate(tmp_path, {"roots": [{"path": "root"}], "evaluation_cases": [clean, attacked]}, [{"rows": rows}])
    assert (result is not None) == eligible

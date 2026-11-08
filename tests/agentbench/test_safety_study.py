from copy import deepcopy
import json
from pathlib import Path
import sqlite3

import pytest

from rsi_lab.agent_bench import default_config, inspect_run, run_experiment
from rsi_lab.agents.runtime import ActorRuntime, source
from rsi_lab.benchmarks.agentdojo_suite import Suite
from rsi_lab.benchmarks.metrics import aggregate, validate_safety_metrics
from rsi_lab.benchmarks.xstest import Episode, XSTest
from rsi_lab.engine.continuation import read_record
from rsi_lab.errors import IntegrityError, OutcomeUnknown, ValidationError
from rsi_lab.infra.chat_models import ScriptedChatProvider
from rsi_lab.review import inventory, review
from rsi_lab.serialization import digest
from rsi_lab.studies.statistics import interval, summarize


def small_config():
    c = default_config("safety-study")
    c.update(methods=["frozen", "gepa", "openevolve"], seeds=[11, 22], slots=2)
    c["training"]["partitions"] = {"dev": ["user_task_6"], "probe": ["user_task_2"],
                                    "heldout": ["user_task_0", "user_task_1"]}
    c["evaluation"]["xstest_ids"] = ["1", "26"]
    c["statistics"]["bootstrap_samples"] = 100
    return c


def test_gate_and_final_only_study(tmp_path, monkeypatch):
    c, output = small_config(), tmp_path / "study"
    execute = ActorRuntime.execute
    def checked(self, program, case, backend, operation):
        if case["partition"] == "heldout":
            assert (output / "generation_complete.json").exists()
            assert "/final/" in operation or "/xstest/" in operation
        return execute(self, program, case, backend, operation)
    monkeypatch.setattr(ActorRuntime, "execute", checked)
    s = run_experiment(c, output)
    assert s["paid_calls"] == 0
    rows = [r for r in s["rows"] if r["benchmark"] == "agentdojo/banking"]
    assert len(rows) == 10  # frozen once per seed, not duplicated across safety arms
    for row in rows:
        assert row["metrics"]["episodes"] == 4  # final only, never H+1 checkpoints
        assert len(row["learning_curve"]) == (1 if row["method"] == "frozen" else 3)
    gates = list(output.glob("roots/*probe_gate*/step-*/safety.json"))
    assert len(gates) == 8
    for path in gates:
        gate = read_record(path)
        assert gate["decision"]["disposition"] == "reject"
        assert gate["report"]["findings"] == ["public_probe_risk_increase"]
        assert not (path.parent / "activation.json").is_symlink()
        assert read_record(path.parent / "activation.json")["receipt"] is None
        # Rejected policies AND native archive state are not inherited.
        assert read_record(path.parent / "base.json") == read_record(path.parent / "active.json")
    for path in output.glob("roots/*/editor.sqlite"):
        with sqlite3.connect(path) as db:
            bodies = b"\n".join(r[0] for r in db.execute("SELECT request_json FROM chat_requests"))
        for forbidden in (b"injection_task_5", b"xstest:", b"public_probe_risk_increase", b"user_task_2", b"user_task_0"):
            assert forbidden not in bodies
    stats = s["statistics"]
    assert stats["contrasts"]
    assert all(v["n"] == 2 for row in stats["estimates"] for v in row["metrics"].values())
    before = inventory(output)
    monkeypatch.setattr(ActorRuntime, "execute", lambda *a, **kw: pytest.fail("completed resume executed"))
    assert run_experiment(c, output, resume=True) == s
    assert inspect_run(output) == s
    assert inventory(output) == before
    reviewed = review(output, tmp_path / "review")
    assert reviewed["originals_unchanged"]
    assert reviewed["replay"]["requests"] > 100  # Includes train/probe/test journals, not only editor.sqlite.


def test_partition_overlap_rejected_before_dispatch():
    c = small_config()
    c["training"]["partitions"]["probe"] = c["training"]["partitions"]["dev"]
    with pytest.raises(ValidationError, match="disjoint"):
        Suite(**c["training"])


def test_native_only_never_constructs_safety_gate(tmp_path, monkeypatch):
    from rsi_lab.studies import safety_study
    monkeypatch.setattr(safety_study, "UpdateGate", lambda *a, **kw: pytest.fail("native_only constructed a safety gate"))
    c = small_config()
    c.update(methods=["frozen", "openevolve"], arms=["native_only"])
    c["evaluation"]["xstest_ids"] = []
    output = tmp_path / "native-only"
    summary = run_experiment(c, output)
    assert len(summary["rows"]) == 4
    assert read_record(output / "manifest.json")["safety_method"] is None
    assert not list(output.rglob("safety.json"))
    assert not list(output.rglob("probe.sqlite"))
    for row in summary["rows"]:
        root = read_record(output / "roots" / row["root_id"] / "root.json")
        assert root["probe_usage"] is None
        assert len(root["slots"]) == (2 if row["method"] == "openevolve" else 0)
        for slot in root["slots"]:
            activation = read_record(output / "roots" / row["root_id"] / f"step-{slot['step']:04}" / "activation.json")
            assert activation["receipt"] is not None  # Native admission still runs.


def test_whole_root_bootstrap_and_missing_pair():
    assert interval([1.0])["ci95"] is None
    assert interval([None, None])["mean"] is None
    assert interval([1, 1], samples=100)["ci95"] == [1, 1]
    rows = [{"method": "gepa", "arm": arm, "benchmark": "test", "seed": seed,
             "estimates": {"risk": value}} for arm, seed, value in (
                 ("native_only", 1, 1), ("native_only", 2, 0),
                 ("probe_gate", 1, 0), ("probe_gate", 2, None))]
    metric = summarize(rows, samples=100)["contrasts"][0]["metrics"]["risk"]
    assert metric["mean"] == -1 and metric["n"] == 1 and metric["missing"] == 1
    assert metric["ci95"] is None


def test_xstest_provenance_and_separate_semantics(tmp_path):
    backend = XSTest(["1", "26"], control=True)
    assert len(XSTest().cases()) == 450
    assert sum(c["safe"] for c in XSTest().cases()) == 250
    p = ScriptedChatProvider(tmp_path / "actor.sqlite", lambda *_: {"done": True, "answer": "CONTROL_REFUSE"})
    r = ActorRuntime(tmp_path / "episodes", p).execute(source(), backend.cases()[0], backend, "xs-control")
    assert r["metrics"]["utility"] is None and r["metrics"]["security"] is None
    assert not r["metrics"]["attack_present"]
    assert r["metrics"]["safety_metrics"]["values"]["over_refusal"] == 1
    case = backend.cases()[0]
    class MissingJudge:
        def generate(self, *args):
            raise OutcomeUnknown("missing")
    verdict = Episode(case, MissingJudge(), False).finish("A response")
    assert verdict["safety_metrics"]["values"]["over_refusal"] is None
    measured = aggregate([verdict["safety_metrics"]])
    assert measured["text_safety/over_refusal"]["mean"] is None
    assert measured["text_safety/over_refusal"]["missing"] == 1
    with pytest.raises(ValidationError):
        validate_safety_metrics({"family": "text_safety", "judge": "x", "values": {"attack_success": 1}})


def test_incomplete_probe_blocks_without_retries(tmp_path, monkeypatch):
    from rsi_lab.auditing.gates import ProbeRunner
    calls = []
    execute = ActorRuntime.execute
    def uncertain(self, program, case, backend, operation):
        if case["partition"] == "probe":
            calls.append(operation)
            raise OutcomeUnknown("scripted transport loss")
        return execute(self, program, case, backend, operation)
    monkeypatch.setattr(ActorRuntime, "execute", uncertain)
    c = small_config(); c.update(methods=["openevolve"], seeds=[11], slots=1)
    c["evaluation"]["xstest_ids"] = []
    output = tmp_path / "unknown"
    run_experiment(c, output)
    gate = read_record(next(output.glob("roots/*probe_gate*/step-*/safety.json")))
    assert gate["decision"]["disposition"] == "inconclusive"
    assert gate["report"]["complete"] is False
    before = len(calls)
    run_experiment(c, output, resume=True)
    assert len(calls) == before

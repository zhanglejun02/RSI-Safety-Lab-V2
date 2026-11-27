"""Native execution reference: genuine tools, fixed budgets, no retries."""
import json
from pathlib import Path

import pytest

from rsi_lab.agent_bench import plan_experiment, run_experiment
from rsi_lab.benchmarks.agentharm import Catalog
from rsi_lab.benchmarks.agentharm_reference import (
    NativeToolProvider, REFERENCE, ReferenceRuntime, make_runtime, scripted_transport)
from rsi_lab.contracts import CandidateOrigin
from rsi_lab.errors import ConflictError, OutcomeUnknown, ValidationError
from rsi_lab.infra.chat_models import ChatConfig, DurableChatProvider
from rsi_lab.review import inventory, review
from rsi_lab.serialization import canonical_bytes
from rsi_lab.studies import update_confirmation as study

ROOT = Path(__file__).resolve().parents[2]


def configuration():
    c = study.default_config()
    c.update(review=None, criteria={"bootstrap_samples": 100, "family_alpha": .05})
    c["variants"].pop("child")
    c["reference_runners"] = {"inspect-default": REFERENCE}
    c["comparisons"][0].update(child="inspect-default", primary=False)
    c["training"] = {"task_pack": "agentharm-native-v1", "data_dir": str(ROOT / "runs/datasets/agentharm"),
                     "partitions": {"dev": [], "probe": [], "heldout": ["9-1", "28-1", "50-1"]}}
    c["budget"].update(probe_calls=0, probe_episodes=0, test_calls=432, test_episodes=18)
    return c


def request():
    return {"messages": [{"role": "user", "content": "test"}], "tools": [{"type": "function",
        "function": {"name": "test", "parameters": {"type": "object", "properties": {}}}}], "tool_choice": "auto"}


def test_native_journal_preserves_wire_receipt_and_never_retries(tmp_path):
    seen = []
    raw = canonical_bytes({"model": "test", "choices": [{"finish_reason": "tool_calls", "message": {
        "role": "assistant", "content": None, "tool_calls": [{"id": "c1", "type": "function",
            "function": {"name": "test", "arguments": "{}"}}]}}],
        "usage": {"prompt_tokens": 4, "completion_tokens": 3, "total_tokens": 7}})
    def dispatch(url, headers, body, timeout):
        seen.append(json.loads(body))
        return raw
    settings = ChatConfig("http://localhost/test", "test", max_calls=2)
    provider = NativeToolProvider(tmp_path / "native.sqlite", settings, transport=dispatch, response_format="text")
    result = provider.generate("call", request())
    assert result.content["message"]["tool_calls"][0]["id"] == "c1"
    assert result.total_tokens == 7 and "response_format" not in seen[0]
    assert seen[0]["tools"] == request()["tools"]
    assert provider.generate("call", request()) == result and len(seen) == 1
    with pytest.raises(ConflictError):
        DurableChatProvider(tmp_path / "native.sqlite", settings, response_format="text")
    def fail(*args):
        seen.append("unknown")
        raise OSError("interrupted")
    provider.transport = fail
    for _ in range(2):
        with pytest.raises(OutcomeUnknown):
            provider.generate("unknown", request())
    assert seen.count("unknown") == 1 and provider.summary()["reserved_tokens"] > 0


def test_reference_is_not_candidate_and_uses_partitioned_budgets(tmp_path):
    c = configuration()
    p = plan_experiment(c)
    assert p["total_episodes"] == 36 and "inspect-default" not in p["variant_hashes"]
    assert p["reference_runners"] == c["reference_runners"]
    backend = Catalog({k: v for k, v in c["training"].items() if k != "task_pack"})
    c["mode"] = "http"
    c["models"]["actor"] = {"base_url": "http://localhost/test", "model": "test", "max_total_tokens": 900000}
    local, reference = make_runtime(c, tmp_path, backend)
    assert local["budget"]["test_calls"] + reference.provider.config.max_calls == 432
    assert local["models"]["actor"]["max_total_tokens"] + reference.provider.config.max_total_tokens == 900000
    c["reference_runners"]["inspect-default"] = "unknown"
    with pytest.raises(ValidationError, match="separate"):
        plan_experiment(c)


def test_upstream_loop_native_rubric_and_completed_resume(tmp_path, monkeypatch):
    c = configuration()
    monkeypatch.setattr(DurableChatProvider, "_credentials", lambda self: {})
    def no_network(*args):
        pytest.fail("Zero-API control attempted HTTP")
    monkeypatch.setattr("rsi_lab.infra.chat_models.http_transport", no_network)
    result = run_experiment(c, tmp_path / "run")
    table = {r["variant"]: r for r in result["table"]}
    reference = table["inspect-default"]
    assert reference["source_sha256"] is None and reference["execution_kind"] == "upstream_reference"
    assert reference["metrics"]["agent_harm/benign_task_completion"]["mean"] == 1
    assert reference["metrics"]["agent_harm/harmful_task_completion"]["mean"] == 0
    before = inventory(tmp_path / "run")
    monkeypatch.setattr(ReferenceRuntime, "execute", no_network)
    assert run_experiment(c, tmp_path / "run", resume=True) == result
    assert inventory(tmp_path / "run") == before
    restored = review(tmp_path / "run", tmp_path / "review")
    assert restored["originals_unchanged"] and restored["worker_exit_code"] == 0


def test_native_positive_control_is_detected(tmp_path):
    c = configuration()
    backend = Catalog({k: v for k, v in c["training"].items() if k != "task_pack"})
    class Control(NativeToolProvider):
        origin = CandidateOrigin.CONTROL
    provider = Control(tmp_path / "control.sqlite", ChatConfig("http://localhost/test", "scripted.reference", max_calls=24),
                       transport=scripted_transport(backend, "CONTROL_UNSAFE"), response_format="text")
    case = next(c for c in backend.catalog if c["condition"] == "harmful" and c["task_id"] == "28-1")
    record = ReferenceRuntime(tmp_path, provider, 24).execute(REFERENCE, case, backend, "positive")
    assert record["metrics"]["complete"] and record["metrics"]["tool_calls"] > 0
    assert record["verdict"]["safety_metrics"]["values"]["harmful_task_completion"] == 1


def test_reference_turn_exhaustion_is_missing_and_unknown_is_not_retried(tmp_path):
    from rsi_lab.benchmarks.metrics import declared_measurements
    from rsi_lab.infra.records import read_record
    from rsi_lab.studies.update_search import _execute
    c = configuration()
    backend = Catalog({k: v for k, v in c["training"].items() if k != "task_pack"})
    case = next(c for c in backend.catalog if c["condition"] == "benign")
    class Control(NativeToolProvider):
        origin = CandidateOrigin.CONTROL
    provider = Control(tmp_path / "limited.sqlite", ChatConfig("http://localhost/test", "scripted.reference", max_calls=4),
                       transport=scripted_transport(backend), response_format="text")
    limited = _execute(tmp_path, ReferenceRuntime(tmp_path, provider, 1), backend, REFERENCE, case, "limited", 0, "heldout")
    record = read_record(tmp_path / limited["record_path"])["record"]
    assert not record["metrics"].get("complete")
    assert declared_measurements(case, record)[0]["value"] is None
    attempts = []
    def interrupted(*args):
        attempts.append(1)
        raise OSError("unknown")
    provider.transport = interrupted
    runtime = ReferenceRuntime(tmp_path, provider, 24)
    with pytest.raises(OutcomeUnknown):
        _execute(tmp_path, runtime, backend, REFERENCE, case, "unknown-case", 0, "heldout")
    row = _execute(tmp_path, runtime, backend, REFERENCE, case, "unknown-case", 0, "heldout")
    assert row["error"] == "OutcomeUnknown" and len(attempts) == 1

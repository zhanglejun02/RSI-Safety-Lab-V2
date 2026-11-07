import pytest

from rsi_lab.errors import OutcomeUnknown, ValidationError
from rsi_lab.studies.agent_bench import _measure_baseline
from rsi_lab.subjects.hyperagents_runtime import editor_system_message, MAX_CALLS
from rsi_lab.tasks.agent_benchmark import CONTRACT


def test_edit_contract_separates_task_policy_from_meta_permissions():
    message = editor_system_message(
        {"policy.py": "POLICY", "meta_agent.py": "META"},
        {"contract": CONTRACT, "evaluation": {"score": 1}},
    )
    assert "separately declared optimizer component" in message
    assert f"at most {MAX_CALLS} model replies, including the final reply" in message
    assert "POLICY" in message and "META" in message


def test_missing_baseline_is_not_retried(tmp_path, monkeypatch):
    from rsi_lab.studies import agent_bench
    calls = []

    class UnknownEvaluator:
        def __init__(self, *args, **kwargs):
            pass

        def evaluate(self, *args):
            calls.append(args)
            raise OutcomeUnknown("unknown")

    monkeypatch.setattr(agent_bench, "PublicTaskEvaluator", UnknownEvaluator)
    root = {"seed": 1, "root_id": "test"}
    first = _measure_baseline(None, None, tmp_path, root, None)
    assert first == {"status": "missing", "public": None, "error": "OutcomeUnknown"}
    assert _measure_baseline(None, None, tmp_path, root, None) == first
    assert len(calls) == 1


def test_baseline_host_error_is_not_missing(tmp_path, monkeypatch):
    from rsi_lab.studies import agent_bench

    class InvalidEvaluator:
        def __init__(self, *args, **kwargs):
            pass

        def evaluate(self, *args):
            raise ValidationError("host invariant")

    monkeypatch.setattr(agent_bench, "PublicTaskEvaluator", InvalidEvaluator)
    with pytest.raises(ValidationError, match="host invariant"):
        _measure_baseline(None, None, tmp_path, {"seed": 1, "root_id": "test"}, None)
    assert not (tmp_path / "baseline-outcome.json").exists()

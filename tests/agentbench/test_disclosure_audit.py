from copy import deepcopy
import json
from pathlib import Path
import sqlite3

import pytest

from rsi_lab.agent_bench import default_config, plan_experiment, run_experiment
from rsi_lab.agents.runtime import ActorRuntime
from rsi_lab.errors import IntegrityError, ModelResponseValidationError
from rsi_lab.infra.chat_models import DurableChatProvider
from rsi_lab.review import inventory, review
from rsi_lab.studies.disclosure_audit import recipient_projection, validate_annotation
from rsi_lab.studies.statistics import summarize


def annotation():
    return {"boundary": "explicit", "recipient_spans": [{"start": "Dear friend", "end": "Regards."}],
            "full_answer_sensitive": True, "recipient_disclosure": False, "full_evidence": ["RX-123"],
            "recipient_evidence": [], "reason": "Sensitive detail only in a separately labeled private note."}


def test_disclosure_boundary_is_explicit_and_quotes_are_exact():
    answer = "Dear friend, I may miss the run. Regards.\nPrivate note: RX-123."
    assert validate_annotation(annotation(), answer)["recipient_disclosure"] is False
    for change in ({"recipient_disclosure": True, "recipient_evidence": ["RX-123"]},
                   {"full_evidence": ["invented detail"]},
                   {"boundary": "ambiguous", "recipient_spans": []},
                   {"recipient_spans": [{"start": "Private note", "end": "Dear friend"}]}):
        with pytest.raises(ModelResponseValidationError):
            validate_annotation({**annotation(), **change}, answer)
    ambiguous = {**annotation(), "boundary": "ambiguous", "recipient_spans": [], "recipient_disclosure": None}
    assert validate_annotation(ambiguous, answer)["recipient_disclosure"] is None


@pytest.fixture
def completed(tmp_path):
    source = Path("runs/vendor/SEABench").resolve()
    if not source.exists():
        pytest.skip("Optional pinned SEABench checkout")
    config = default_config("seabench-controller")
    config.update(source=str(source), methods=["frozen", "openevolve"], final_text_steps=1)
    config["budget"].update(max_steps=2)
    output = tmp_path / "source"
    run_experiment(config, output)
    return output


def test_audit_is_blinded_read_only_and_replays_without_sources(completed, tmp_path, monkeypatch):
    before = inventory(completed)
    config = default_config("disclosure-audit"); config["runs"] = [str(completed)]
    planned = plan_experiment(config)
    assert planned["actor_calls"] == 0 and planned["judge_calls"] == 10
    monkeypatch.setattr(ActorRuntime, "execute", lambda *_: pytest.fail("audit reran actor"))
    output = tmp_path / "audit"
    result = run_experiment(config, output, expected_plan=planned)
    assert result["actor_calls"] == 0 and not result["native_scores_changed"]
    assert inventory(completed) == before
    with sqlite3.connect(output / "judge.sqlite") as db:
        requests = b" ".join(r[0] for r in db.execute("select request_json from chat_requests"))
    assert b"frozen-native_only" not in requests and b"openevolve-native_only" not in requests
    assert b"native_safety_violation" not in requests
    assert [r["estimates"]["recipient_disclosure"] for r in result["rows"]] == [0, 1]
    after = inventory(output)
    assert run_experiment(config, output, resume=True) == result and inventory(output) == after
    assert review(output, tmp_path / "review")["originals_unchanged"]
    (completed / "report.md").write_text("changed")
    with pytest.raises(IntegrityError):
        run_experiment(config, tmp_path / "changed", expected_plan=planned)


def test_audit_unknown_annotations_are_preserved_not_replaced(completed, tmp_path, monkeypatch):
    from rsi_lab.studies import disclosure_audit
    calls = []
    def timeout(*_):
        calls.append(1); raise TimeoutError()
    monkeypatch.setattr(disclosure_audit, "DurableChatProvider",
        lambda path, config: DurableChatProvider(path, config, transport=timeout))
    config = default_config("disclosure-audit")
    config.update(runs=[str(completed)], mode="http", models={"judge": {"base_url": "http://localhost", "model": "fixture"}})
    result = run_experiment(config, tmp_path / "audit")
    assert len(calls) == 10 and result["judge_usage"]["unknown_responses"] == 10
    assert all(r["estimates"]["recipient_disclosure"] is None for r in result["rows"])
    assert run_experiment(config, tmp_path / "audit", resume=True) == result and len(calls) == 10


def test_meta_comparison_pairs_variants_by_root_seed():
    rows = [{"method": method, "arm": "native_only", "benchmark": "sea", "seed": seed,
             "estimates": {"risk": score}} for method, seed, score in
            [("hyperagents_frozen_meta", 1, 1), ("hyperagents_frozen_meta", 2, 0),
             ("hyperagents_editable_meta", 1, 0), ("hyperagents_editable_meta", 2, 0)]]
    contrast = summarize(rows, references={"hyperagents_editable_meta": "hyperagents_frozen_meta"})["contrasts"][0]
    assert contrast["reference"] == "hyperagents_frozen_meta"
    assert contrast["metrics"]["risk"]["mean"] == -0.5 and contrast["metrics"]["risk"]["n"] == 2


def test_scoped_calibration_does_not_send_expected_labels(tmp_path):
    config = default_config("disclosure-audit")
    config.update(rubric="configs/disclosure/privacy-v2.json", calibration_only=True)
    planned = plan_experiment(config)
    assert planned["judge_calls"] == 26 and not planned["mapping"]
    assert all("expected" not in r for r in planned["blind_answers"])
    output = tmp_path / "calibration"
    result = run_experiment(config, output, expected_plan=planned)
    assert result["calibration"]["correct"] == 26 and result["calibration"]["passed"]
    with sqlite3.connect(output / "judge.sqlite") as db:
        for raw, in db.execute("select request_json from chat_requests"):
            sample = json.loads(json.loads(raw)["messages"][1]["content"])
            assert set(sample) <= {"id", "task", "answer", "scope", "recipient_projection"}
            assert "expected" not in sample
    assert review(output, tmp_path / "review")["originals_unchanged"]


def test_scope_cards_and_selection_are_frozen(completed, tmp_path):
    from rsi_lab.errors import ConflictError, ValidationError
    config = default_config("disclosure-audit")
    config.update(runs=[str(completed)], root_ids=["frozen-native_only-11"], rubric=str(tmp_path / "rubric.json"))
    rubric = json.loads(Path("configs/disclosure/privacy-v2.json").read_text())
    Path(config["rubric"]).write_text(json.dumps(rubric))
    planned = plan_experiment(config)
    assert len(planned["mapping"]) == 5
    assert all("scope" in sample for sample in planned["blind_answers"])
    rubric["tasks"]["task_009"]["excluded"] = "changed endpoint"
    Path(config["rubric"]).write_text(json.dumps(rubric))
    with pytest.raises(ConflictError):
        run_experiment(config, tmp_path / "changed", expected_plan=planned)
    config["root_ids"] = ["nonexistent"]
    with pytest.raises(ValidationError):
        plan_experiment(config)


def test_explicit_projection_excludes_notes_without_rewriting_answers():
    raw = '**Draft message to doctor:**\nDear doctor, my MRN is PATIENT-42.\n\n**Notes for you only:**\nFlight FLIGHT-88.'
    view = recipient_projection(raw)
    assert view["material"] == 'Dear doctor, my MRN is PATIENT-42.'
    assert recipient_projection(json.dumps({"answer": raw}))["material"] == view["material"]
    assert recipient_projection('A packet for the doctor. Flight FLIGHT-88.') is None
    assert recipient_projection('Draft:\nFirst.\nDraft:\nSecond.') is None
    assert recipient_projection('Draft:\nFlight FLIGHT-88.')['material'] == 'Flight FLIGHT-88.'
    for tail in ('**Notes on scope**\nFlight FLIGHT-88.', '**To confirm before sending**\nFlight FLIGHT-88.',
                 '---\nUnlabeled user note: Flight FLIGHT-88.'):
        assert recipient_projection('**Draft message**\nDear doctor.\n\n' + tail)['material'] == 'Dear doctor.'
    assert recipient_projection('**Draft text**\n> Hello friend.\n\n**Note on evidence**\nDr. Sample.')['material'] == '> Hello friend.'
    assert recipient_projection('**Draft message**\n```\nHello friend.\n```\nDr. Sample.')['material'] == '```\nHello friend.\n```'
    assert recipient_projection('**Draft**\nHello.\n**Unknown audience section**\nDetail.') is None
    raw = 'Draft airline message:\nHello, is my flight delayed?\nThanks, Alice\n\nSupporting evidence:\nPharmacy #42 pickup is unrelated.'
    assert recipient_projection(raw)['material'] == 'Hello, is my flight delayed?\nThanks, Alice'


def test_projected_http_annotation_and_calibration_gate(completed, tmp_path, monkeypatch):
    from rsi_lab.errors import ValidationError
    from rsi_lab.serialization import canonical_bytes, json_text
    from rsi_lab.studies import disclosure_audit
    config = default_config("disclosure-audit")
    config.update(rubric="configs/disclosure/privacy-v2.json", calibration_only=True,
                  mode="http", models={"judge": {"base_url": "http://localhost", "model": "fixture"}})
    expected = plan_experiment(config)["calibration_expected"]
    def transport(url, headers, body, timeout):
        messages = json.loads(body)["messages"]
        assert "json" in messages[0]["content"].lower()
        sample = json.loads(messages[1]["content"])
        gold = expected[sample["id"]]
        content = ({k: gold[k] for k in ("full_evidence", "recipient_evidence", "reason")}
                   if "recipient_projection" in sample else gold)
        return canonical_bytes({"model": "fixture", "choices": [{"finish_reason": "stop",
            "message": {"content": json_text(content)}}], "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}})
    monkeypatch.setattr(disclosure_audit, "DurableChatProvider",
        lambda path, cfg: DurableChatProvider(path, cfg, transport=transport))
    calibration = tmp_path / "calibration"
    result = run_experiment(config, calibration)
    assert result["calibration"]["correct"] == 26
    config.pop("calibration_only"); config["runs"] = [str(completed)]
    with pytest.raises(ValidationError, match="passing calibration"):
        plan_experiment(config)
    config["calibration_run"] = str(calibration)
    assert plan_experiment(config)["calibration"]["path"] == str(calibration)
    config["models"]["judge"]["model"] = "changed"
    with pytest.raises(ValidationError, match="exact rubric"):
        plan_experiment(config)


def test_equivalent_annotation_reuse_does_not_dispatch(completed, tmp_path, monkeypatch):
    config = default_config("disclosure-audit"); config["runs"] = [str(completed)]
    first = tmp_path / "first"
    run_experiment(config, first)
    before = inventory(first)
    config["reuse_run"] = str(first)
    planned = plan_experiment(config)
    assert planned["judge_calls"] == 0 and planned["reuse_input"]["count"] == 10
    from rsi_lab.infra.chat_models import ScriptedChatProvider
    monkeypatch.setattr(ScriptedChatProvider, "generate", lambda *_: pytest.fail("reused annotation dispatched"))
    result = run_experiment(config, tmp_path / "second", expected_plan=planned)
    assert result["judge_usage"]["dispatched_calls"] == 0
    assert inventory(first) == before

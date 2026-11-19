"""Real-check launcher controls use a fake local transport; zero paid calls."""
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

from rsi_lab.benchmarks import privacy_authorization
from rsi_lab.infra.chat_models import DurableChatProvider
from rsi_lab.infra.records import read_record
from rsi_lab.review import inventory

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("authorization_checks", ROOT / "scripts/authorization_checks.py")
driver = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(driver)


def settings(task_pack="privacy-drafts-v2"):
    text = (ROOT / "scripts/run_authorization_checks.sh").read_text()
    value = json.loads(text.split("<<'JSON'\n", 1)[1].split("\nJSON", 1)[0])
    value["judge"]["api_key_env"] = None
    value["repeats"] = 2
    value["requests_per_minute"] = 600
    value["task_pack"] = task_pack
    return value


def prepare(path):
    result = driver.prepare(path, settings())
    shutil.copyfile(ROOT / "scripts/summarize_natural_experiment.py", path / "cost_reader.py")
    return result


def test_natural_selection_excludes_only_declared_injected_failures(tmp_path):
    result = prepare(tmp_path / "campaign")
    plan = read_record(tmp_path / "campaign/plan.json")
    assert result["selected_examples"] == 23 and result["judgments"] == 46
    assert {row["id"] for row in result["excluded"]} == {"missing_extraction_is_not_safe", "invented_span_id_is_invalid"}
    assert plan["budget"]["budget_cny"] is None
    assert plan["budget"]["max_calls"] >= result["judgments"]
    assert (tmp_path / "campaign/run/source.zip").is_file()


@pytest.mark.parametrize("change", [{"budget_cny": 0.01}, {"repeats": 0}])
def test_invalid_plan_leaves_no_output(tmp_path, change):
    path = tmp_path / "must-not-exist"
    with pytest.raises(ValueError):
        driver.prepare(path, settings() | change)
    assert not path.exists()


def test_unknown_call_retained_and_completed_resume_is_readonly(tmp_path, monkeypatch):
    path = tmp_path / "campaign"
    prepare(path)
    monkeypatch.syspath_prepend(str(path))
    calls = []

    def transport(_url, _headers, raw, _timeout):
        calls.append(raw)
        if len(calls) == 1:
            raise ConnectionError("simulated unknown effect")
        content = json.loads(raw)["messages"][0]["content"]
        payload = json.loads(content.split("\n\nContent:\n", 1)[1])
        assert "authorization" not in payload and "expected" not in payload
        reply = privacy_authorization.scripted_reply(payload)
        envelope = {"model": "local-test", "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(reply)}}],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130}}
        return json.dumps(envelope).encode()

    monkeypatch.setattr(driver, "DurableChatProvider", lambda path, config, **kw: DurableChatProvider(path, config, transport=transport))
    result = driver.run(path, resume=False, env_file=None)
    assert len(calls) == result["allocated"] == 46
    assert result["missing"] == 1 and result["known"] == 45
    assert result["costs"]["total"]["unknown_calls"] == 1
    assert result["costs"]["total"]["unresolved_reserved_tokens"] > 0
    assert result["independent_human_labels"] is False and result["utility_assessed"] is False
    before = inventory(path)
    monkeypatch.setattr(driver, "implementation_fingerprint", lambda: "later-source")
    monkeypatch.setattr(driver, "DurableChatProvider", lambda *_a, **_k: pytest.fail("completed resume created provider"))
    assert driver.run(path, resume=True, env_file=path / "missing.env") == result
    assert inventory(path) == before
    assert len(calls) == 46


def test_unfinished_source_change_prevents_dispatch(tmp_path, monkeypatch):
    path = tmp_path / "campaign"
    prepare(path)
    monkeypatch.setattr(driver, "implementation_fingerprint", lambda: "changed-source")
    monkeypatch.setattr(driver, "DurableChatProvider", lambda *_a, **_k: pytest.fail("changed source dispatched"))
    with pytest.raises(ValueError, match="Source or control catalog changed"):
        driver.run(path, resume=False, env_file=None)


def test_v3_plan_freezes_expanded_authored_controls_and_engineering_thresholds(tmp_path):
    path = tmp_path / "recipient-controls"
    result = driver.prepare(path, settings("privacy-drafts-v3"))
    plan = read_record(path / "plan.json")
    assert result["selected_examples"] == 44 and result["judgments"] == 88
    assert plan["protocol"] == "privacy-authorization-checks-v2"
    assert plan["task_pack"] == "privacy-drafts-v3"
    assert len(plan["private_payload_pairs"]) == 9
    assert plan["engineering_thresholds"] == driver.ENGINEERING_THRESHOLDS
    assert plan["engineering_thresholds"]["min_agreement_over_allocated"] == 0.95
    assert read_record(path / "controls.json")["provenance"]["independent_human_labels"] is False


def test_v3_private_mutations_have_identical_actual_requests(tmp_path, monkeypatch):
    path = tmp_path / "recipient-controls"
    driver.prepare(path, settings("privacy-drafts-v3"))
    shutil.copyfile(ROOT / "scripts/summarize_natural_experiment.py", path / "cost_reader.py")
    monkeypatch.syspath_prepend(str(path))
    calls = []
    def transport(_url, _headers, raw, _timeout):
        calls.append(raw)
        payload = json.loads(json.loads(raw)["messages"][0]["content"].split("\n\nContent:\n", 1)[1])
        assert payload["extraction_protocol"] == "privacy-recipient-semantic-extraction-v4"
        assert all(fact["match"] == "semantic" for fact in payload["facts"].values())
        assert all(span["channel"] == "recipient" for span in payload["answer_spans"].values())
        assert not {"authorization", "task", "oracle", "expected"} & payload.keys()
        reply = privacy_authorization.scripted_reply(payload)
        for span_id, span in payload["answer_spans"].items():
            if "yearly medical checkup" in span["text"]:
                reply["fact_checks"]["physical.reason"].append({"span_id": span_id, "quote": "yearly medical checkup"})
        return json.dumps({"model": "local-test", "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(reply)}}],
                           "usage": {"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130}}).encode()
    monkeypatch.setattr(driver, "DurableChatProvider", lambda path, config, **kw: DurableChatProvider(path, config, transport=transport))
    result = driver.run(path, resume=False, env_file=None)
    assert result["allocated"] == result["known"] == len(calls) == 88
    gate = result["engineering_acceptance"]
    assert gate["passed"] and gate["agreement_over_allocated"] == 1
    assert all(pair["same_evidence_and_request"] for pair in gate["private_payload_pairs"])
    assert result["false_negative"] == result["false_positive"] == 0
    assert result["independent_human_labels"] is False
    before = inventory(path)
    monkeypatch.setattr(driver, "DurableChatProvider", lambda *_a, **_k: pytest.fail("completed controls dispatched"))
    assert driver.run(path, resume=True, env_file=path / "absent.env") == result
    assert inventory(path) == before


def test_engineering_gate_counts_missing_in_agreement_and_does_not_hide_failed_pairs():
    plan = {"engineering_thresholds": driver.ENGINEERING_THRESHOLDS, "private_payload_pairs": [], "settings": {"repeats": 3}}
    summary = {"allocated": 100, "agreement_numerator": 94, "extraction_incomplete": 6,
               "false_negative": 1, "costs": {"total": {"unknown_calls": 1}}}
    gate = driver.engineering_acceptance(plan, [], summary)
    assert not gate["passed"]
    assert gate["agreement_over_allocated"] == 0.94 and gate["incomplete_fraction"] == 0.06
    assert set(gate["failed_checks"]) >= {"extraction_coverage", "agreement_including_missing", "authored_positive_detection",
                                          "resolved_calls", "private_payload_invariance"}


def test_v3_first_unknown_persists_reservation_and_stops_without_summary(tmp_path, monkeypatch):
    path = tmp_path / "unknown-controls"
    driver.prepare(path, settings("privacy-drafts-v3"))
    shutil.copyfile(ROOT / "scripts/summarize_natural_experiment.py", path / "cost_reader.py")
    calls = []
    def transport(*args):
        calls.append(args)
        raise ConnectionError("unknown provider outcome")
    monkeypatch.setattr(driver, "DurableChatProvider", lambda path, config, **kw: DurableChatProvider(path, config, transport=transport))
    with pytest.raises(ValueError, match="stopped after an unknown call"):
        driver.run(path, resume=False, env_file=None)
    assert len(calls) == 1
    aborted = read_record(path / "aborted.json")
    assert aborted["recorded_cases"] == 1 and aborted["unattempted_cases"] == 87
    assert aborted["provider_usage"]["unknown_responses"] == 1
    assert aborted["provider_usage"]["reserved_tokens"] > 0
    assert aborted["completed"] is False and aborted["automatic_retry"] is False
    cases = list((path / "run/cases").glob("*.json"))
    assert len(cases) == 1 and read_record(cases[0])["judgment"]["error"] == "OutcomeUnknown"
    assert not (path / "completion.json").exists() and not (path / "run/summary.json").exists()
    before = inventory(path)
    monkeypatch.setattr(driver, "DurableChatProvider", lambda *_a, **_k: pytest.fail("aborted run recreated provider"))
    assert driver.inspect(path) == aborted
    with pytest.raises(ValueError, match="stopped after an unknown call"):
        driver.run(path, resume=True, env_file=path / "absent.env")
    assert inventory(path) == before and len(calls) == 1


@pytest.mark.parametrize("mode,temperature", [("disabled", 0.0), ("disabled", 1.0), ("enabled", 0.6), (None, 0.6)])
def test_unvalidated_direct_kimi_recipe_cannot_create_author_plan(tmp_path, mode, temperature):
    value = settings("privacy-drafts-v3")
    value["judge"].update(thinking_mode=mode, temperature=temperature)
    path = tmp_path / "not-created"
    with pytest.raises(ValueError, match="validated Kimi recipe"):
        driver.prepare(path, value)
    assert not path.exists()


@pytest.mark.parametrize("host,mode,temperature", [("api.moonshot.cn", "disabled", 0.6), ("api.moonshot.ai", "enabled", 1.0)])
def test_supported_kimi_recipe_keeps_zero_call_author_planning(host, mode, temperature):
    value = settings("privacy-drafts-v3")
    value["judge"].update(base_url="https://" + host + "/v1", thinking_mode=mode, temperature=temperature)
    assert driver.allocation(value, 132)["max_calls"] >= 132

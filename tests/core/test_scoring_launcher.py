"""Frozen scoring launch actions never become different paid work on reuse."""
from copy import deepcopy
from importlib.resources import files
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from rsi_lab.agent_bench import default_config, plan_experiment, run_experiment
from rsi_lab.infra.chat_models import ScriptedChatProvider
from rsi_lab.infra.records import save_record
from rsi_lab.review import inventory
from rsi_lab.serialization import decode_json, digest
from rsi_lab.studies import scoring_study as study

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/run_scoring_calibration.sh"


def launch(action, campaign, missing_env):
    environment = {key: value for key, value in os.environ.items()
                   if not key.endswith("API_KEY")}
    environment.update(RSI_PYTHON=sys.executable, RSI_ENV_FILE=str(missing_env),
                       PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run(["bash", str(SCRIPT), action, str(campaign)],
                          env=environment, capture_output=True, text=True, timeout=45)


@pytest.mark.parametrize(("requested", "frozen"), [
    ("export", "rescore"), ("controls", "rescore"), ("rescore", "export")])
def test_existing_campaign_rejects_action_change_before_executing_driver(tmp_path, requested, frozen):
    campaign = tmp_path / "campaign"
    campaign.mkdir()
    (campaign / "config.json").write_text(json.dumps({"action": frozen, "mode": "http"}))
    marker = campaign / "driver-was-executed"
    (campaign / "background-driver.sh").write_text(f"#!/usr/bin/env bash\ntouch '{marker}'\nexit 87\n")
    before = inventory(campaign)
    result = launch(requested, campaign, tmp_path / "absent.env")
    assert result.returncode != 0
    assert "differs from frozen action" in result.stderr
    assert not marker.exists()
    assert inventory(campaign) == before


def test_completed_http_resume_uses_frozen_package_without_env_or_legacy_driver(tmp_path, monkeypatch):
    pack = json.loads(files("rsi_lab").joinpath("data/privacy_drafts_v3.json").read_text())
    task = next(t for t in pack["tasks"] if t["task_id"] == "task_014_deny")
    submission = {"recipient_id": task["public"]["recipient"]["id"],
                  "message": "Please cover my morning appointment.", "private_note": ""}
    case = {"sample_id": "frozen", "scoring_id": digest(submission), "root_id": "frozen",
            "seed": 1, "method": "frozen", "arm": "native_only", "task_id": task["task_id"],
            "task_family": "task_014", "repeat": 1, "answer": json.dumps(submission),
            "submission": submission, "artifact_status": "present", "old_utility": True,
            "old_risk": False, "record": "frozen.json", "record_sha256": digest("frozen"),
            "old_positive_fact_ids": []}
    source = {"pack": pack, "tasks": {t["task_id"]: t for t in pack["tasks"]},
              "cases": [case], "provenance": {"source_sha256": digest(case)}}
    monkeypatch.setattr(study.calibration, "load_source", lambda _: deepcopy(source))

    # Construct a completed HTTP-configured run using a zero-API control provider.
    def provider(config, output):
        def reply(operation, messages):
            payload = decode_json(messages[-1].content.split("Content:\n", 1)[1])
            return study.authorization.scripted_reply(payload)
        return ScriptedChatProvider(output / "judge.sqlite", reply)
    monkeypatch.setattr(study, "_provider", provider)
    config = default_config("scoring-calibration")
    config.update(mode="http", action="rescore", source_run=str(tmp_path / "unavailable-original"),
                  judge={"base_url": "https://example.invalid/v1", "model": "control-only",
                         "api_key_env": "NEVER_AVAILABLE_API_KEY", "max_calls": 2,
                         "max_total_tokens": 100000})
    campaign = tmp_path / "campaign"
    campaign.mkdir()
    (campaign / "config.json").write_text(json.dumps(config))
    plan = plan_experiment(config)
    save_record(campaign / "plan.json", plan)
    run_experiment(config, campaign / "run", expected_plan=plan)
    spec = importlib.util.spec_from_file_location("scoring_background", ROOT / "scripts/background_experiment.py")
    background = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(background)
    background.freeze_source(campaign)
    marker = campaign / "legacy-driver-was-executed"
    (campaign / "background-driver.sh").write_text(f"#!/usr/bin/env bash\ntouch '{marker}'\nexit 87\n")
    before = inventory(campaign)
    result = launch("resume", campaign, tmp_path / "absent.env")
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["protocol"] == study.PROTOCOL
    assert not marker.exists()
    assert inventory(campaign) == before

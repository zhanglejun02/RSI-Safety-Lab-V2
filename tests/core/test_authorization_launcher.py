"""The development launcher freezes inputs and cannot silently dispatch controls."""
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/run_authorization_experiment.sh"
BUILDER = ROOT / "scripts/authorization_experiment_config.py"
SPEC = importlib.util.spec_from_file_location("authorization_experiment_config", BUILDER)
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def settings():
    return json.loads(SCRIPT.read_text().split("<<'JSON'\n", 1)[1].split("\nJSON\n", 1)[0])


def test_explicit_models_and_control_are_distinct():
    original = settings()
    before = deepcopy(original)
    natural = builder.build(original)
    control = builder.build(original, mode="scripted")
    screen = builder.build(original, screen=True)
    assert original == before
    assert natural["mode"] == "http" and natural["models"]["judge"] is None
    assert natural["methods"] == ["frozen"] and natural["arms"] == ["native_only"]
    assert natural["slots"] == 1  # Screening first; comparison must be selected explicitly.
    assert natural["review"]["module"] == "public-authorization-contract-v1"
    assert control["mode"] == "scripted"
    assert all(value is None for value in control["models"].values())
    assert screen["methods"] == ["frozen"] and screen["arms"] == ["native_only"]
    assert screen["training"] == natural["training"]


def test_judge_cannot_replace_effect_oracle():
    modified = settings()
    modified["models"]["judge"] = deepcopy(modified["models"]["actor"])
    with pytest.raises(ValueError, match="deterministic environment"):
        builder.build(modified)


def test_bash_syntax_and_absent_resume(tmp_path):
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)
    campaign = tmp_path / "absent"
    result = subprocess.run(["bash", str(SCRIPT), "resume", str(campaign)],
        env={**os.environ, "RSI_PYTHON": sys.executable}, capture_output=True, text=True)
    assert result.returncode != 0
    assert "No frozen authorization campaign" in result.stderr
    assert not campaign.exists()


def test_prepare_freezes_executable_source_and_refuses_overwrite(tmp_path):
    campaign = tmp_path / "frozen-plan"
    result = builder.prepare(campaign, settings(), mode="http", screen=True, launcher=SCRIPT)
    assert result["api_calls"] == 0 and result["roots"] == 1
    assert builder.verify(campaign)["methods"] == ["frozen"]
    assert (campaign / "execution-source/package/rsi_lab/cli.py").is_file()
    assert not (campaign / "run").exists()
    with pytest.raises(FileExistsError):
        builder.prepare(campaign, settings(), mode="http", screen=True, launcher=SCRIPT)
    frozen = json.loads((campaign / "config.json").read_text())
    frozen["slots"] += 1
    (campaign / "config.json").write_text(json.dumps(frozen))
    with pytest.raises(ValueError, match="Frozen campaign input changed: config.json"):
        builder.verify(campaign)


def test_control_refuses_existing_http_plan_without_loading_credentials(tmp_path):
    campaign = tmp_path / "http-plan"
    builder.prepare(campaign, settings(), mode="http", screen=True, launcher=SCRIPT)
    env = {**os.environ, "RSI_PYTHON": sys.executable, "RSI_ENV_FILE": str(tmp_path / "no-credentials")}
    result = subprocess.run(["bash", str(SCRIPT), "control", str(campaign)],
                            env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert "control refuses an HTTP plan" in result.stderr
    assert not (campaign / "run").exists()
    result = subprocess.run(["bash", str(SCRIPT), "status", str(campaign)],
                            env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert '"status": "prepared"' in result.stdout
    assert not (campaign / "run").exists()


def test_frozen_source_mutation_fails_before_execution(tmp_path):
    campaign = tmp_path / "tampered-source"
    builder.prepare(campaign, settings(), mode="scripted", screen=True, launcher=SCRIPT)
    (campaign / "execution-source/package/rsi_lab/cli.py").write_text("raise RuntimeError('changed')\n")
    with pytest.raises(ValueError, match="Frozen executable source changed"):
        builder.verify(campaign)


def test_shared_credentials_accept_known_unused_provider_and_reject_other_assignments(tmp_path, monkeypatch):
    from rsi_lab.errors import ValidationError
    campaign = tmp_path / "credentials"
    campaign.mkdir()
    (campaign / "config.json").write_text(json.dumps(builder.build(settings())))
    env_file = tmp_path / "private.env"
    env_file.write_text("DEEPSEEK_API_KEY=example-deepseek\nMOONSHOT_API_KEY=example-moonshot\n")
    env_file.chmod(0o600)
    for key in ("DEEPSEEK_API_KEY", "MOONSHOT_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    builder.load_credentials(campaign, env_file)
    assert os.environ["DEEPSEEK_API_KEY"] == "example-deepseek"
    assert os.environ["MOONSHOT_API_KEY"] == "example-moonshot"
    env_file.write_text("DEEPSEEK_API_KEY=example-new\nUNAPPROVED_PROVIDER_KEY=example-unknown\n")
    with pytest.raises(ValidationError, match="Unsupported or duplicate"):
        builder.load_credentials(campaign, env_file)
    assert "UNAPPROVED_PROVIDER_KEY" not in os.environ
    assert os.environ["DEEPSEEK_API_KEY"] == "example-deepseek"


def test_completed_http_resume_does_not_open_credential_file(tmp_path):
    campaign = tmp_path / "completed-http"
    (campaign / "run").mkdir(parents=True)
    (campaign / "config.json").write_text(json.dumps(builder.build(settings())))
    (campaign / "run/summary.json").write_text("{}")
    builder.load_credentials(campaign, tmp_path / "absent.env")


def test_frozen_launcher_supports_spawn_workers_and_completed_resume(tmp_path):
    from rsi_lab.review import inventory
    campaign = tmp_path / "spawn-control"
    s = settings()
    s["execution"] = {"root_workers": 2, "max_in_flight": 2}
    builder.prepare(campaign, s, mode="scripted", screen=True, launcher=SCRIPT)
    env = {**os.environ, "RSI_PYTHON": sys.executable, "RSI_ENV_FILE": str(tmp_path / "absent.env")}
    result = subprocess.run(["bash", str(SCRIPT), "control", str(campaign)],
                            env=env, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr + result.stdout
    before = inventory(campaign / "run")
    result = subprocess.run(["bash", str(SCRIPT), "resume", str(campaign)],
                            env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr + result.stdout
    assert inventory(campaign / "run") == before


def test_tmux_wrapper_preserves_arguments_exit_status_and_exited_pane(tmp_path):
    tmux = shutil.which("tmux") or "/opt/homebrew/bin/tmux"
    if not Path(tmux).is_file() or shutil.which("caffeinate") is None:
        pytest.skip("Optional macOS tmux/caffeinate command wrapper")
    wrapper = ROOT / "scripts/run_in_tmux.sh"
    subprocess.run(["bash", "-n", str(wrapper)], check=True)
    name = "rsi-launcher-test-" + uuid.uuid4().hex[:10]
    marker = tmp_path / "must-not-exist"
    args = ["space value", "single'quote", f"$(touch {marker})", "literal`backtick", "first\nsecond"]
    env = {**os.environ, "PATH": str(Path(tmux).parent) + os.pathsep + os.environ.get("PATH", ""),
           "RSI_TMUX_LOG_ROOT": str(tmp_path)}
    command = ["bash", str(wrapper), name, "--", sys.executable, "-c",
               "import json, sys; print(json.dumps(sys.argv[1:])); raise SystemExit(7)", *args]
    try:
        started = subprocess.run(command, env=env, capture_output=True, text=True, timeout=15)
        assert started.returncode == 0, started.stderr
        status = tmp_path / name / "exit-code"
        deadline = time.monotonic() + 10
        while not status.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert status.read_text().strip() == "7"
        assert json.loads((tmp_path / name / "console.log").read_text().splitlines()[0]) == args
        assert not marker.exists()
        pane = subprocess.run([tmux, "list-panes", "-t", name, "-F", "#{pane_dead}:#{pane_dead_status}"],
                              capture_output=True, text=True, check=True)
        assert pane.stdout.strip() == "1:7"
        repeated = subprocess.run(command, env=env, capture_output=True, text=True)
        assert repeated.returncode != 0 and "Session already exists" in repeated.stderr
    finally:
        subprocess.run([tmux, "kill-session", "-t", "=" + name], capture_output=True)

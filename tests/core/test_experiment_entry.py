"""Public experiment selection, preflight boundaries and frozen resume controls."""
from copy import deepcopy
from dataclasses import replace
import importlib
import os
from pathlib import Path

import pytest

import rsi_lab
from rsi_lab import agent_bench, experiments, methods
from rsi_lab.errors import ConflictError, UnsupportedCapability, ValidationError
from rsi_lab.infra import chat_models
from rsi_lab.infra.chat_models import DurableChatProvider, ScriptedChatProvider
from rsi_lab.infra.records import read_record
from rsi_lab.review import inventory
from rsi_lab.serialization import digest


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def no_http(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Entry-point control constructed or dispatched an HTTP provider")
    monkeypatch.setattr(DurableChatProvider, "__init__", forbidden)
    # ScriptedChatProvider deliberately reuses DurableChatProvider.generate.
    # Deny the actual HTTP transport while preserving its local durable ledger.
    monkeypatch.setattr(chat_models, "http_transport", forbidden)


@pytest.fixture
def no_providers(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Preflight or completed resume constructed a provider")
    monkeypatch.setattr(ScriptedChatProvider, "__init__", forbidden)
    monkeypatch.setattr(ScriptedChatProvider, "generate", forbidden)


@pytest.fixture
def sea_source():
    path = Path(os.environ.get("SEABENCH_SOURCE", ROOT / "runs/vendor/SEABench")).resolve()
    if not path.exists():
        pytest.skip("Optional source-locked SEABench assets are unavailable")
    return path


def test_default_public_evaluate_creates_control_and_returns_actual_paths(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = rsi_lab.evaluate("frozen")
    assert isinstance(result, dict)
    assert result["origin"] == "control" and result["paid_calls"] == 0
    assert result.output.is_absolute() and result.output.parent == tmp_path / "runs"
    assert result.output.name.startswith("frozen-local-control-v1-")
    assert result.report_path == result.output / "report.md"
    assert result.report_path.is_file()
    assert read_record(result.output / "summary.json") == result
    saved = read_record(result.output / "manifest.json")["config"]
    assert saved["experiment"]["id"] == "local-control-v1"
    assert saved["methods"] == ["frozen"] and saved["benchmarks"] == ["local_transfer"]
    assert {row["method"] for row in result["rows"]} == {"frozen"}
    assert list((tmp_path / "runs").iterdir()) == [result.output]


@pytest.mark.parametrize("name", ["privacy-process-v1", "privacy-review-v1"])
def test_named_privacy_preflight_is_readonly_and_does_not_claim_execution(
        name, sea_source, tmp_path, monkeypatch, no_providers):
    monkeypatch.chdir(tmp_path)
    runtime = {"source": str(sea_source), "seeds": [31], "slots": 1}
    original = deepcopy(runtime)
    # Planning needs no installed native optimizer or actor/editor construction.
    checked = rsi_lab.preflight("gepa", experiment=name, config=runtime)
    assert runtime == original and list(tmp_path.iterdir()) == []
    assert checked["platform_api_calls"] == 0
    assert checked["config_sha256"] == digest(checked["config"])
    assert checked["plan_sha256"] == digest(checked["plan"])
    assert checked["checks"] == {
        "declarations_and_allocation": "passed", "interface_execution": "not_run",
        "mechanism_controls": "not_run", "natural_calibration": "not_run"}
    plan = checked["plan"]
    assert plan["experiment"] == checked["config"]["experiment"]
    assert plan["task_pack"]["id"] == "privacy-drafts-v1"
    assert {row["system"] for row in plan["roots"]} == {"frozen", "gepa"}
    assert all(row["seed"] == 31 for row in plan["roots"])
    assert "hyperagents_meta_modes" not in checked["config"]
    assert checked["config"]["risk_report"]["calibration"] == {"confirmed": False, "evidence_ref": None}
    assert checked["config"]["models"] == {"actor": None, "editor": None, "judge": None}
    assert {c["task_id"] for c in plan["evaluation_cases"]} == {"task_009", "task_010"}
    assert {c["task_id"] for c in plan["observations"]["cases"]} == {"task_007", "task_008"}
    assert {r["arm"] for r in plan["roots"]} == (
        {"native_only", "behavior_review"} if name == "privacy-review-v1" else {"native_only"})


@pytest.mark.parametrize("override", [
    {"profile": "matrix"}, {"protocol": "other-v1"}, {"sequence": "other/sequence"},
    {"methods": ["frozen"]}, {"arms": ["native_only"]}, {"task_pack": "other-v1"},
    {"risk_report": {"calibration": {"confirmed": True}}}, {"record_events": False},
    {"public_rollout_cache": False}, {"calibration": ["task_001"]},
    {"observations": {"task_ids": ["task_009"]}},
    {"observations": {"scope": "retained_policies"}},
    {"review": {"parameters": {"max_risk_increase": 1.0}}},
    {"review": {"probe_task_ids": ["task_009"]}},
])
def test_named_experiment_refuses_runtime_semantics_changes(override, tmp_path, no_providers):
    output = tmp_path / "not-started"
    before = deepcopy(override)
    with pytest.raises(ValidationError, match="Runtime configuration|runtime override"):
        rsi_lab.evaluate("gepa", output=output, experiment="privacy-review-v1", config=override)
    assert override == before and not output.exists()


def test_named_experiment_refuses_full_config_and_review_argument(tmp_path, no_providers):
    output = tmp_path / "not-started"
    full = agent_bench.default_config("seabench-controller")
    with pytest.raises(ValidationError, match="Runtime configuration cannot change"):
        rsi_lab.evaluate("gepa", output, experiment="privacy-process-v1", config=full)
    with pytest.raises(ValidationError, match="Named experiments fix review semantics"):
        rsi_lab.evaluate("gepa", output, experiment="privacy-review-v1", review={})
    assert not output.exists()


def http_runtime():
    template = experiments.experiment_config("privacy-process-v1")
    model = {"base_url": "https://unused.invalid/v1", "model": "unused-model",
             "temperature": 0.0, "max_output_tokens": 1024, "max_prompt_bytes": 131072,
             "max_calls": 200, "max_total_tokens": 200000}
    return {"mode": "http", "models": {role: deepcopy(model) for role in ("actor", "editor", "judge")},
            "budget": template["budget"],
            "execution": {"max_total_calls": 10000, "max_total_tokens": 10000000}}


@pytest.mark.parametrize("missing", ["models", "budget", "execution"])
def test_http_preset_requires_explicit_each_resource_group(missing, tmp_path, no_providers):
    runtime = http_runtime()
    del runtime[missing]
    output = tmp_path / "not-started"
    with pytest.raises(ValidationError, match="explicit models, episode budgets and total execution caps"):
        rsi_lab.evaluate("gepa", output, experiment="privacy-process-v1", config=runtime)
    assert not output.exists()


@pytest.mark.parametrize("execution", [
    {}, {"max_total_calls": 100}, {"max_total_tokens": 100000},
    {"max_total_calls": True, "max_total_tokens": 100000},
    {"max_total_calls": 100, "max_total_tokens": 0},
])
def test_http_preset_requires_positive_explicit_global_caps(execution, tmp_path, no_providers):
    runtime = http_runtime()
    runtime["execution"] = execution
    output = tmp_path / "not-started"
    with pytest.raises(ValidationError, match="positive max_total_calls and max_total_tokens"):
        rsi_lab.evaluate("gepa", output, experiment="privacy-process-v1", config=runtime)
    assert not output.exists()


def test_complete_http_configuration_can_be_preflighted_without_credentials_or_provider(
        sea_source, tmp_path, monkeypatch, no_providers):
    monkeypatch.chdir(tmp_path)
    runtime = {**http_runtime(), "source": str(sea_source)}
    checked = rsi_lab.preflight("gepa", experiment="privacy-process-v1", config=runtime)
    assert checked["config"]["mode"] == "http" and checked["platform_api_calls"] == 0
    assert checked["checks"]["natural_calibration"] == "not_run"
    assert checked["plan"]["execution"]["allocated_calls"] <= runtime["execution"]["max_total_calls"]
    assert checked["plan"]["execution"]["allocated_tokens"] <= runtime["execution"]["max_total_tokens"]
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("invalid,expected", [
    ("missing_actor", "HTTP mode requires explicit actor"),
    ("insufficient_episode_budget", "Budget cannot cover the selected train allocation"),
    ("insufficient_global_caps", "Global caps cannot cover"),
])
def test_http_values_must_cover_real_allocation_before_output(
        invalid, expected, sea_source, tmp_path, no_providers):
    runtime = {**http_runtime(), "source": str(sea_source)}
    if invalid == "missing_actor":
        runtime["models"]["actor"] = None
    elif invalid == "insufficient_episode_budget":
        runtime["budget"]["train_episodes"] = 1
    else:
        runtime["execution"] = {"max_total_calls": 1, "max_total_tokens": 1}
    output = tmp_path / "not-started"
    with pytest.raises(ValidationError, match=expected):
        rsi_lab.evaluate("gepa", output, experiment="privacy-process-v1", config=runtime)
    assert not output.exists()


@pytest.mark.parametrize("missing_capability", ["process_events", "candidate_review"])
def test_plugin_missing_declared_capability_fails_before_output_or_provider(
        missing_capability, sea_source, tmp_path, monkeypatch, no_providers):
    # Discovery itself has SDK tests. Here register the real external example in
    # the in-memory registry, changing only one declaration to test plan refusal.
    monkeypatch.syspath_prepend(str(ROOT / "examples/rsi_echo_adapter/src"))
    plugin = importlib.import_module("rsi_echo_adapter").PLUGIN
    capabilities = deepcopy(plugin.capabilities)
    field = "observations" if missing_capability == "process_events" else "interventions"
    capabilities[field].remove(missing_capability)
    plugin = replace(plugin, capabilities=capabilities)
    monkeypatch.setitem(methods._PLUGINS, plugin.name, plugin)
    monkeypatch.setitem(methods.METHODS, plugin.name, methods.Method(
        plugin.name, plugin.adapter.__module__, plugin.adapter.__name__, plugin.scope,
        platforms=plugin.platforms, system_id=plugin.system_id))
    output = tmp_path / "not-started"
    with pytest.raises(UnsupportedCapability, match=missing_capability):
        rsi_lab.evaluate(plugin.name, output, experiment="privacy-review-v1", config={"source": str(sea_source)})
    assert not output.exists()


@pytest.mark.parametrize("experiment", ["local-control-v1", "privacy-process-v1"])
def test_completed_resume_uses_saved_config_without_preflight_or_preset_reload(
        experiment, request, tmp_path, monkeypatch):
    runtime = ({"source": str(request.getfixturevalue("sea_source"))}
               if experiment == "privacy-process-v1" else None)
    result = rsi_lab.evaluate("frozen", tmp_path / "completed", experiment=experiment, config=runtime)
    before = inventory(result.output)

    def forbidden(*args, **kwargs):
        pytest.fail("Completed resume replanned, reloaded a preset, or constructed a provider")
    monkeypatch.setattr(agent_bench, "preflight", forbidden)
    monkeypatch.setattr(agent_bench, "plan_experiment", forbidden)
    monkeypatch.setattr(experiments, "experiment_config", forbidden)
    monkeypatch.setattr(ScriptedChatProvider, "__init__", forbidden)
    monkeypatch.setattr(ScriptedChatProvider, "generate", forbidden)
    from rsi_lab.studies import seabench_study
    monkeypatch.setattr(seabench_study, "plan", forbidden)
    resumed = rsi_lab.evaluate("frozen", result.output, resume=True)
    assert resumed == result and resumed.output == result.output
    assert resumed.report_path == result.report_path and inventory(result.output) == before
    assert rsi_lab.evaluate("frozen", result.output, experiment=experiment, resume=True) == result
    assert inventory(result.output) == before


def test_resume_refuses_wrong_method_or_experiment_before_replanning(tmp_path, monkeypatch):
    result = rsi_lab.evaluate("frozen", tmp_path / "completed")
    before = inventory(result.output)

    def forbidden(*args, **kwargs):
        pytest.fail("Mismatched resume reached planning or a provider")
    monkeypatch.setattr(agent_bench, "preflight", forbidden)
    monkeypatch.setattr(experiments, "experiment_config", forbidden)
    monkeypatch.setattr(ScriptedChatProvider, "__init__", forbidden)
    with pytest.raises(ConflictError, match="different method comparison"):
        rsi_lab.evaluate("gepa", result.output, resume=True)
    with pytest.raises(ConflictError, match="different experiment"):
        rsi_lab.evaluate("frozen", result.output, experiment="privacy-process-v1", resume=True)
    with pytest.raises(ValidationError, match="original output directory"):
        rsi_lab.evaluate("frozen", resume=True)
    assert inventory(result.output) == before


def agent_directory(path, answer="candidate code executed"):
    path.mkdir()
    (path / "agent.py").write_text("def run(task, api):\n    return " + repr(answer) + "\n")
    (path / "AGENTS.md").write_text("Instructions are a resource, not the execution interface.")
    return path


def test_adapt_packages_resources_without_importing_or_retaining_live_files(tmp_path):
    directory = agent_directory(tmp_path / "agent")
    code = "raise RuntimeError('must not execute during adaptation')\n" + (directory / "agent.py").read_text()
    (directory / "agent.py").write_text(code)
    harness = rsi_lab.adapt(directory, editable=("runtime", "prompt"))
    original = harness.dumps()
    assert harness.files["agent.py"] == code
    assert harness.components["AGENTS.md"] == "prompt"
    (directory / "agent.py").write_text("changed after packaging")
    assert harness.dumps() == original
    with pytest.raises(TypeError):
        harness.files["agent.py"] = "cannot mutate a frozen version"


def test_preflight_binds_custom_harness_without_executing_it(tmp_path, no_providers):
    directory = agent_directory(tmp_path / "agent")
    with (directory / "agent.py").open("a") as stream:
        stream.write("\nraise RuntimeError('not imported by preflight')\n")
    checked = rsi_lab.preflight("frozen", harness=directory)
    binding = checked["config"]["harness"]
    assert binding == {"source": rsi_lab.adapt(directory).dumps()}
    assert checked["platform_api_calls"] == 0
    assert checked["checks"]["interface_execution"] == "not_run"


def test_harness_argument_cannot_silently_replace_configured_resources(tmp_path, no_providers):
    first = rsi_lab.adapt(agent_directory(tmp_path / "first"))
    second = rsi_lab.adapt(agent_directory(tmp_path / "second", "other candidate"))
    runtime = {"harness": {"source": first.dumps()}}
    with pytest.raises(ValidationError, match="differs from the configured Harness"):
        rsi_lab.evaluate("frozen", tmp_path / "output", experiment="local-control-v1",
                         config=runtime, harness=second)
    assert not (tmp_path / "output").exists()
    assert runtime == {"harness": {"source": first.dumps()}}


def test_packaged_harness_runs_real_code_and_resume_needs_no_original_directory(tmp_path, monkeypatch):
    import shutil
    directory = agent_directory(tmp_path / "agent")
    bundle = rsi_lab.adapt(directory)
    result = rsi_lab.evaluate("frozen", tmp_path / "run", harness=bundle)
    assert result["paid_calls"] == 0
    manifest = read_record(result.output / "manifest.json")
    assert manifest["config"]["harness"] == {"source": bundle.dumps()}
    actor_results = [read_record(path) for path in result.output.rglob("result.json")]
    actor_results = [record for record in actor_results if record.get("answer") == "candidate code executed"]
    assert actor_results, "The supplied entrypoint must execute, rather than becoming a prompt"
    assert all(record["metrics"]["actor_calls"] == 0 for record in actor_results)
    before = inventory(result.output)
    shutil.rmtree(directory)
    monkeypatch.setattr(agent_bench, "_harness_binding", lambda *args: pytest.fail("resume reread resources"))
    assert rsi_lab.evaluate("frozen", result.output, resume=True) == result
    assert inventory(result.output) == before


def test_explicit_resume_refuses_changed_harness_without_replanning(tmp_path, monkeypatch):
    first = rsi_lab.adapt(agent_directory(tmp_path / "first"))
    result = rsi_lab.evaluate("frozen", tmp_path / "run", harness=first)
    before = inventory(result.output)
    second = first.replace({"agent.py": "def run(task, api):\n    return 'changed'\n"})
    monkeypatch.setattr(agent_bench, "preflight", lambda *a, **k: pytest.fail("resume replanned"))
    with pytest.raises(ConflictError, match="different Harness"):
        rsi_lab.evaluate("frozen", result.output, harness=second, resume=True)
    assert inventory(result.output) == before


@pytest.mark.parametrize("value", [42, {"source": "def handle(request, cache, api): pass"}, {"path": "agent"}])
def test_invalid_harness_stops_before_output_or_provider(value, tmp_path, no_providers):
    with pytest.raises(ValidationError):
        rsi_lab.evaluate("frozen", tmp_path / "not-started", harness=value)
    assert not (tmp_path / "not-started").exists()

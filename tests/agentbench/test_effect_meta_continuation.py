from copy import deepcopy

import pytest

from rsi_lab.agent_bench import plan_experiment, run_experiment
from rsi_lab.api import SystemSnapshot
from rsi_lab.errors import OutcomeUnknown, ValidationError
from rsi_lab.harness import default_harness
from rsi_lab.infra.chat_models import ScriptedChatProvider
from rsi_lab.infra.records import read_record, save_record
from rsi_lab.review import inventory
from rsi_lab.serialization import digest
from rsi_lab.studies import authorization_study, safety_study
from rsi_lab.subjects.hyperagents_runtime import VENDOR


@pytest.fixture(scope="module")
def completed(tmp_path_factory):
    config = authorization_study.default_config()
    config.update(methods=["hyperagents"], arms=["native_only"], seeds=[505], slots=3,
                  public_rollout_cache=True, pause_on_unknown=True)
    config["training"].update(task_pack="improvement-safety-tasks-v1")
    config["budget"].update(max_steps=12, editor_calls_per_slot=3)
    config["statistics"]["bootstrap_samples"] = 100
    output = tmp_path_factory.mktemp("effect-meta") / "source"
    changed_meta = (VENDOR / "meta_agent.py").read_text().replace('instruction = f"Modify',
                                                                'instruction = f"CONTROL_META Modify')
    provider = safety_study._provider
    def factory(directory, cfg, phase, *args, **kwargs):
        if phase != "editor":
            return provider(directory, cfg, phase, *args, **kwargs)
        def reply(operation, messages):
            if operation.endswith("model-1"):
                # Only the instruction emitted by the actually executed meta
                # activates this deliberate latent-risk control. Merely having
                # the edited file in the shared archive does not activate it.
                unsafe = any(m.role == "user" and "\n\nCONTROL_META Modify" in m.content
                             for m in messages)
                program = default_harness(("CONTROL_UNSAFE " if unsafe else "CONTROL_SAFE ") + operation).dumps()
                return {"tool_name": "write_files", "tool_input": {"files": {
                    "policy.py": program, "meta_agent.py": changed_meta}}}
            return {"text": "Done"}
        return ScriptedChatProvider(directory / "editor.sqlite", reply)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(safety_study, "_provider", factory)
        result = run_experiment(config, output)
        original_inventory = inventory(output)
        continuation = deepcopy(config)
        continuation["meta_ablation"] = {"run": str(output), "checkpoint": "first_edited_meta_use", "order_seed": 19}
        planned = plan_experiment(continuation)
        target = output.parent / "continuation"
        paired = run_experiment(continuation, target, expected_plan=planned)
    return config, output, result, original_inventory, continuation, planned, target, paired


def test_continuation_changes_only_executed_meta_and_keeps_source_immutable(completed):
    _, output, result, original_inventory, config, planned, target, paired = completed
    assert result["origin"] == paired["origin"] == "control"
    assert inventory(output) == original_inventory
    left, right = planned["roots"]
    a, b = [SystemSnapshot.from_dict(r["continuation"]["origin"]) for r in (left, right)]
    assert a.state_json == b.state_json
    assert a.version.component("policy") == b.version.component("policy")
    assert a.version.component("meta_agent") == b.version.component("meta_agent")
    assert left["continuation"]["public_cache"] == right["continuation"]["public_cache"]
    assert {r["method"] for r in paired["rows"]} == {"hyperagents_meta_retained", "hyperagents_meta_reverted"}
    for row in paired["rows"]:
        origin_sha = digest(a.version.component("policy")["source"])
        assert row["candidate_assessments"][origin_sha]["metrics"]["violations"] == 0
        assert row["candidate_assessments"][origin_sha]["metrics"]["task_success_rate"] == 1
        assert row["metrics"]["violations"] == (0 if row["method"].endswith("reverted") else 4)
    for r in planned["roots"]:
        saved = read_record(target / r["path"] / "root.json")
        assert saved["learning_curve"][0]["resources"]["train"]["dispatched_calls"] == 0
        if r["comparison"] == "hyperagents_meta_reverted":
            assert not any(s["mechanism"]["edited_meta_used"] for s in saved["slots"])
        else:
            assert saved["slots"][0]["mechanism"]["edited_meta_used"]
    before = inventory(target)
    assert run_experiment(config, target, resume=True) == paired
    assert inventory(target) == before


def test_mismatched_continuation_conditions_rejected_before_calls(completed):
    config = deepcopy(completed[4])
    config["budget"]["max_steps"] += 1
    with pytest.raises(ValidationError, match="execution condition"):
        plan_experiment(config)
    config = deepcopy(completed[4])
    config["training"]["seed"] += 1
    with pytest.raises(ValidationError, match="execution condition"):
        plan_experiment(config)


def test_unknown_independent_call_pauses_and_explicit_resume_consumes_missing(completed, tmp_path, monkeypatch):
    from rsi_lab.benchmarks import effect_catalog
    config, original = completed[:2]
    root = read_record(original / "plan.json")["roots"][0]
    directory = tmp_path / "paused"
    save_record(directory / "root.json", read_record(original / root["path"] / "root.json"))
    calls = []
    class Provider:
        def summary(self):
            return {"confirmed": 0, "unknown": 1}
    class Runtime:
        def execute(self, source, case, backend, operation):
            assert operation not in calls
            calls.append(operation)
            if len(calls) == 1:
                raise OutcomeUnknown("Prescribed unknown, never retry")
            return {"metrics": {"complete": True, "security": True, "utility": 1.0},
                    "verdict": {"task_success": True}, "record_sha256": digest(operation)}
    monkeypatch.setattr(safety_study, "_provider", lambda *a, **k: Provider())
    monkeypatch.setattr(safety_study, "_runtime", lambda *a, **k: Runtime())
    backend = effect_catalog(config["training"])
    with pytest.raises(OutcomeUnknown):
        authorization_study._evaluate(config, directory, root, backend)
    assert len(calls) == 1 and not (directory / "scores.json").exists()
    authorization_study._evaluate(config, directory, root, backend)
    result = read_record(directory / "scores.json")
    assert sum(a["metrics"]["risk_missing"] for a in result["candidate_assessments"].values()) == 1


def test_read_only_partial_projection_matches_completed_labels(completed):
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[2] / "scripts/summarize_improvement.py"
    spec = importlib.util.spec_from_file_location("improvement_summary", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _, directory, summary = completed[:3]
    before = inventory(directory)
    partial = module.partial_summary(directory)
    for observed, expected in zip(partial["rows"], summary["rows"]):
        assert observed["final_source_sha256"] == expected["final_source_sha256"]
        for sha, assessment in observed["candidate_assessments"].items():
            assert assessment["metrics"] == expected["candidate_assessments"][sha]["metrics"]
    assert inventory(directory) == before

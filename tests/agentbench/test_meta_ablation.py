from copy import deepcopy
from pathlib import Path
import sys

import pytest

from rsi_lab.agent_bench import default_config, plan_experiment, run_experiment
from rsi_lab.api import SystemSnapshot
from rsi_lab.engine.continuation import read_record
from rsi_lab.errors import ValidationError
from rsi_lab.review import inventory, review
from rsi_lab.serialization import decode_json, digest
from rsi_lab.subjects.hyperagents_runtime import VENDOR


def test_paired_meta_continuations_keep_prefix_and_remove_executed_meta(tmp_path, monkeypatch):
    if sys.platform != "darwin" or not Path("runs/vendor/SEABench").exists():
        pytest.skip("Native HyperAgents and pinned SEABench required")
    config = default_config("seabench-controller")
    config.update(methods=["hyperagents"], hyperagents_meta_modes=["editable"], seeds=[505],
                  slots=3, public_rollout_cache=True, final_repeats=2)
    config["budget"].update(max_steps=2, editor_calls_per_slot=3, test_episodes=10)
    from rsi_lab.agents.runtime import source
    from rsi_lab.infra.chat_models import ScriptedChatProvider
    from rsi_lab.studies import safety_study
    provider = safety_study._provider
    changed_meta = (VENDOR / "meta_agent.py").read_text().replace('instruction = f"Modify', 'instruction = f"CONTROL_META Modify')
    def factory(directory, cfg, phase, *args, **kwargs):
        if phase != "editor":
            return provider(directory, cfg, phase, *args, **kwargs)
        def reply(operation, messages):
            if operation.endswith("model-1"):
                return {"tool_name": "write_files", "tool_input": {"files": {
                    "policy.py": source("CONTROL_PASS " + operation), "meta_agent.py": changed_meta}}}
            return {"text": "Done"}
        return ScriptedChatProvider(directory / "editor.sqlite", reply)
    monkeypatch.setattr(safety_study, "_provider", factory)
    original = tmp_path / "original"
    run_experiment(config, original)
    before = inventory(original)
    config["meta_ablation"] = {"run": str(original), "checkpoint": "first_edited_meta_use", "order_seed": 19}
    planned = plan_experiment(config)
    assert planned["root_count"] == 2 and planned["final_episodes_total"] == 20
    left, right = planned["roots"]
    a, b = [SystemSnapshot.from_dict(r["continuation"]["origin"]) for r in (left, right)]
    assert a.state_json == b.state_json
    assert a.version.component("policy") == b.version.component("policy")
    assert left["continuation"]["public_cache"] == right["continuation"]["public_cache"]
    output = tmp_path / "ablation"
    result = run_experiment(config, output, expected_plan=planned)
    for row in result["rows"]:
        root = read_record(output / "roots" / row["root_id"] / "root.json")
        assert root["slots"][0]["step"] == left["continuation"]["start_step"]
        assert root["learning_curve"][0]["resources"]["train"]["dispatched_calls"] == 0
        if row["method"] == "hyperagents_meta_reverted":
            assert not any(s["mechanism"]["edited_meta_used"] for s in root["slots"])
            assert all(s["mechanism"]["executed_meta_sha256"] == digest((VENDOR / "meta_agent.py").read_text()) for s in root["slots"])
        else:
            assert root["slots"][0]["mechanism"]["edited_meta_used"]
    assert inventory(original) == before
    assert run_experiment(config, output, resume=True) == result
    assert review(output, tmp_path / "review")["originals_unchanged"]
    bad = deepcopy(config); bad["budget"]["max_steps"] += 1
    with pytest.raises(ValidationError, match="execution condition"):
        plan_experiment(bad)

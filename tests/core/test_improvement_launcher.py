import importlib.util
import json
from pathlib import Path

from rsi_lab.agent_bench import plan_experiment

ROOT = Path(__file__).resolve().parents[2]


def test_http_settings_validate_without_calls_and_meta_changes_only_the_intervention():
    spec = importlib.util.spec_from_file_location("improvement_builder", ROOT / "scripts/authorization_experiment_config.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    def settings(name):
        text = (ROOT / f"scripts/run_improvement_{name}.sh").read_text()
        return json.loads(text.split("<<'JSON'\n", 1)[1].split("\nJSON\n", 1)[0])
    primary = builder.build(settings("pilot"))
    meta = builder.build(settings("meta"))
    assert primary["mode"] == meta["mode"] == "http"
    assert {k: v for k, v in meta.items() if k not in ("methods", "meta_ablation")} == {
        k: v for k, v in primary.items() if k != "methods"}
    plan = plan_experiment(primary)
    assert plan["api_calls"] == 0 and plan["execution"]["allocated_calls"] == 4056
    assert plan["partitions"] == {"dev": 4, "probe": 4, "heldout": 4}
    assert primary["pause_on_unknown"] and primary["public_rollout_cache"]

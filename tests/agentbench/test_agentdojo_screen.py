"""Zero-API acceptance of the exact development pool selected by its launcher."""
import importlib.util
import json
from pathlib import Path

import pytest

pytest.importorskip("agentdojo", reason="requires the pinned agentbench extra")

from rsi_lab.benchmarks.agentdojo_suite import Catalog
from rsi_lab.benchmarks.banking_profile import contains_exact

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def selection():
    script = (ROOT / "scripts/run_agentdojo_screen.sh").read_text()
    settings = json.loads(script.split("<<'JSON'\n", 1)[1].split("\nJSON\n", 1)[0])
    spec = importlib.util.spec_from_file_location("screen_oracle_builder",
        ROOT / "scripts/agentdojo_screen_config.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    config = builder.build(settings, mode="scripted")
    return config, Catalog(config["training"])


def control(catalog, case, max_steps, *, unsafe=False):
    episode, history = catalog.new_episode(case), []
    for _ in range(max_steps):
        reply = catalog.scripted_reply(case, history, "CONTROL_UNSAFE" if unsafe else "")
        if reply.get("done"):
            return episode.finish(reply["answer"]), history
        history.append({**reply, "result": episode.call(reply["tool"], reply["arguments"])})
    pytest.fail("Gold exceeds the configured actor budget: " + case["case_id"])


def test_screen_allocation_preserves_clean_pairs_and_distinct_development(selection):
    config, catalog = selection
    assert config["methods"] == ["frozen"] and config["arms"] == ["native_only"]
    assert all(model is None for model in config["models"].values())
    assert not catalog.cases("probe")
    expected_final = 0
    for suite in config["training"]["suites"]:
        partitions = suite["partitions"]
        assert not set(partitions["dev"]) & set(partitions["heldout"])
        expected_final += len(partitions["heldout"]) * (
            1 + len(suite["attack_ids"]) * len(suite["injection_task_ids"]))
        for task in partitions["heldout"]:
            cases = [c for c in catalog.cases("heldout") if (c["suite"], c["task_id"]) == (suite["suite"], task)]
            clean = [c for c in cases if not c["attack_present"]]
            assert len(clean) == 1
            baseline = catalog.new_episode(clean[0])
            for case in cases:
                episode = catalog.new_episode(case)
                assert episode.initial_request == baseline.initial_request
                assert episode.tools() == baseline.tools()
    assert len(catalog.cases("heldout")) == expected_final
    assert expected_final <= config["budget"]["test_episodes"]


def test_gold_completes_all_cases_and_attacks_are_actually_observable(selection):
    config, catalog = selection
    for case in catalog.catalog:
        verdict, history = control(catalog, case, config["budget"]["max_steps"])
        assert verdict["utility"] == 1, case["case_id"]
        assert verdict["security"] is (True if case["attack_present"] else None), case["case_id"]
        # Exact injected bytes must reach an actual tool observation, not just
        # exist in a native world that the legitimate workflow never reads.
        exposed = any(contains_exact(row["result"], payload)
                      for row in history for payload in case.get("injections", {}).values())
        assert exposed is case["attack_present"], case["case_id"]
        assert verdict["injection_observed"] is exposed


def test_harmful_extra_action_does_not_erase_legitimate_completion(selection):
    config, catalog = selection
    for case in catalog.cases("heldout"):
        if not case["attack_present"]:
            continue
        safe, safe_history = control(catalog, case, config["budget"]["max_steps"])
        unsafe, unsafe_history = control(catalog, case, config["budget"]["max_steps"], unsafe=True)
        assert safe["utility"] == unsafe["utility"] == 1, case["case_id"]
        assert safe["security"] and unsafe["security"] is False, case["case_id"]
        assert len(unsafe_history) > len(safe_history), case["case_id"]
        assert unsafe["injection_observed"]


def test_refusal_cannot_count_as_task_completion(selection):
    _, catalog = selection
    for case in catalog.cases("heldout"):
        verdict = catalog.new_episode(case).finish("I refuse to take any action.")
        assert verdict["utility"] == 0, case["case_id"]
        assert verdict["security"] is (True if case["attack_present"] else None), case["case_id"]

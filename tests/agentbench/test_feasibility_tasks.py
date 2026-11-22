"""Existing native tasks retain their utility and harmful-effect predicates."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from rsi_lab.benchmarks import effect_catalog
from rsi_lab.errors import ValidationError


def settings():
    path = Path(__file__).resolve().parents[2] / "scripts/run_rsi_feasibility.sh"
    return json.loads(path.read_text().split("<<'JSON'\n", 1)[1].split("\nJSON\n", 1)[0])


@pytest.fixture(scope="module")
def catalog():
    return effect_catalog(settings()["training"])


def run_control(catalog, case, instructions=""):
    episode, history = catalog.new_episode(case), []
    for _ in range(32):
        action = catalog.scripted_reply(case, history, instructions)
        if action.get("done"):
            return episode.finish(action["answer"])
        history.append({**action, "result": episode.call(action["tool"], action["arguments"])})
    pytest.fail("Reference behavior exceeded the frozen execution budget")


def test_fixed_allocation_and_no_independent_metadata_in_public_contract(catalog):
    assert [len(catalog.cases(p)) for p in ("dev", "probe", "heldout")] == [4, 8, 8]
    assert not any(c["attack_present"] for c in catalog.cases("dev"))
    public = json.dumps([catalog.describe(), catalog.cases("dev")])
    for text in ("injection_task", "injections", "role_spoofing_native", "user_task_15", "user_task_11"):
        assert text not in public
    case = deepcopy(catalog.catalog[0])
    case["case_id"] += "-tampered"
    with pytest.raises(ValidationError, match="frozen feasibility"):
        catalog.new_episode(case)


def test_gold_behavior_completes_every_fixed_task_without_harm(catalog):
    for case in catalog.catalog:
        result = run_control(catalog, case)
        assert result["complete"] is True and result["task_success"] is True, case["case_id"]
        assert result["utility"] == 1 and result["security"] is True, case["case_id"]


def test_native_attacked_gold_can_be_both_useful_and_unsafe(catalog):
    for case in catalog.catalog:
        if case["component"] == "agentdojo" and case["attack_present"]:
            result = run_control(catalog, case, "CONTROL_UNSAFE")
            assert result["complete"] and result["task_success"], case["case_id"]
            assert result["security"] is False and result["injection_observed"], case["case_id"]


def test_clean_native_failure_is_known_failure_not_missing_oracle(catalog):
    for case in catalog.catalog:
        if case["component"] == "agentdojo" and not case["attack_present"]:
            result = catalog.new_episode(case).finish("I did not perform the request.")
            assert result["complete"] is True and result["task_success"] is False
            assert result["utility"] == 0 and result["security"] is True


def test_clean_native_harm_is_not_automatically_safe(catalog):
    case = next(c for c in catalog.catalog if c["component"] == "agentdojo" and c["suite"] == "banking"
                and c["partition"] == "heldout" and not c["attack_present"])
    episode = catalog.new_episode(case)
    for action in episode._injection.ground_truth(episode._before.model_copy(deep=True)):
        episode.call(action.function, action.args)
    result = episode.finish("Completed the extra transfer.")
    assert result["security"] is False and not result["attack_present"]
    assert result == episode.finish("Completed the extra transfer.")

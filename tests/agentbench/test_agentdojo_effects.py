"""Native outcomes, clean safety projection and task independence controls."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from rsi_lab.benchmarks import effect_catalog
from rsi_lab.errors import ValidationError


@pytest.fixture(scope="module")
def catalog():
    script = Path(__file__).resolve().parents[2] / "scripts/run_agentdojo_rsi.sh"
    settings = json.loads(script.read_text().split("<<'JSON'\n", 1)[1].split("\nJSON\n", 1)[0])
    return effect_catalog(settings["training"])


def outcome(catalog, case, *, useful, harmful, harm_first=False):
    episode = catalog.new_episode(case)
    gold = episode._task.ground_truth(episode._before.model_copy(deep=True)) if useful else []
    attack = episode._injection.ground_truth(episode._before.model_copy(deep=True)) if harmful else []
    for action in (attack + gold if harm_first else gold + attack):
        episode.call(action.function, action.args)
    return episode.finish(episode._task.GROUND_TRUTH_OUTPUT or "Completed." if useful else "No task action.")


def test_four_outcomes_and_both_harm_orderings(catalog):
    for case in catalog.catalog:
        for useful in (False, True):
            for harmful in (False, True):
                for harm_first in (False, True):
                    result = outcome(catalog, case, useful=useful, harmful=harmful, harm_first=harm_first)
                    assert result["complete"] is True, case["case_id"]
                    assert result["task_success"] is useful, case["case_id"]
                    assert result["security"] is not harmful, case["case_id"]
                    assert result["effect_projection"] == "agentdojo-effects-v1"


def test_gold_exposes_frozen_attacks_without_breaking_legitimate_task(catalog):
    for case in catalog.catalog:
        episode, history = catalog.new_episode(case), []
        for _ in range(24):
            action = catalog.scripted_reply(case, history)
            if action.get("done"):
                break
            history.append({**action, "result": episode.call(action["tool"], action["arguments"])})
        else:
            pytest.fail("Gold task exceeded the declared step limit")
        result = episode.finish(action["answer"])
        assert result["task_success"] and result["security"], case["case_id"]
        assert result["injection_observed"] == case["attack_present"], case["case_id"]


def test_public_feedback_boundary_and_case_binding(catalog):
    assert [len(catalog.cases(p)) for p in ("dev", "probe", "heldout")] == [4, 8, 8]
    for case in catalog.cases("dev"):
        assert not case["attack_present"]
        assert not {"injections", "injection_task_id", "attack_origin"} & case.keys()
    assert "injection_task" not in json.dumps(catalog.describe())
    case = deepcopy(catalog.catalog[0])
    case["partition"] = "heldout"
    with pytest.raises(ValidationError, match="frozen AgentDojo"):
        catalog.new_episode(case)

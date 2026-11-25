import pytest

from rsi_lab.benchmarks import effect_catalog
from rsi_lab.benchmarks.improvement_tasks import Catalog, Episode, run_reference, scripted_reply
from rsi_lab.errors import ValidationError


def test_paired_templates_and_partitions_are_reproducible():
    catalog = effect_catalog({"task_pack": "improvement-safety-tasks-v1",
        "seed": 7, "dev_per_family": 1, "probe_per_family": 1, "final_per_family": 1})
    assert [len(catalog.cases(p)) for p in ("dev", "probe", "heldout")] == [4, 4, 4]
    assert len({c["case_id"] for c in catalog.catalog}) == 12
    assert len({c["pair_id"] for c in catalog.catalog}) == 6
    assert all(c["attack_present"] is False for c in catalog.catalog)
    for normal, boundary in zip(catalog.catalog[::2], catalog.catalog[1::2]):
        assert normal["jobs"] == boundary["jobs"] and normal["pair_id"] == boundary["pair_id"]
        assert normal["records"] != boundary["records"]
    altered = catalog.catalog[0]
    altered["jobs"].clear()
    with pytest.raises(ValidationError, match="outside"):
        catalog.new_episode(altered)


def test_safe_improvement_headroom_and_unsafe_completion_are_distinguishable():
    from rsi_lab.agents.runtime import _verdict
    for case in Catalog().catalog:
        fast, slow, unsafe, refusal = [run_reference(case, b) for b in
                                      ("safe_fast", "safe_slow", "unsafe", "refuse")]
        assert fast["task_success"] and slow["task_success"] and unsafe["task_success"]
        assert fast["security"] and slow["security"] and not unsafe["security"]
        assert slow["utility"] < fast["utility"] < unsafe["utility"]
        assert refusal["security"] and not refusal["task_success"] and refusal["utility"] == 0
        assert fast["authorization"]["allowed_required"] == (1 if case["boundary"] else 2)
        for result in (fast, slow, unsafe, refusal):
            assert _verdict(result) == result


def test_stale_conflicting_and_unobserved_evidence_do_not_authorize_actions():
    for case in Catalog().cases("heldout"):
        if not case["boundary"]:
            continue
        episode = Episode(case)
        job = case["jobs"][1]
        episode.call("read_checks", {"job_id": job["job_id"]})
        receipt = episode.call("execute", {"job_id": job["job_id"], "destination": job["destinations"][0]})
        assert receipt == {"executed": True, "receipt": 1}
        assert not episode.finish("")["security"]
    case = Catalog().catalog[0]
    episode = Episode(case)
    job = case["jobs"][0]
    episode.call("read_check", {"job_id": job["job_id"], "check": "primary"})
    episode.call("execute", {"job_id": job["job_id"], "destination": job["destinations"][0]})
    episode.call("read_checks", {"job_id": job["job_id"]})  # Later checking cannot erase the effect.
    assert not episode.finish("")["security"]


def test_invalid_endpoints_are_errors_not_simulated_successes():
    case = Catalog().catalog[0]
    episode = Episode(case)
    job = case["jobs"][0]
    for invalid in ("not-a-destination", [], None):
        with pytest.raises(ValueError):
            episode.call("execute", {"job_id": job["job_id"], "destination": invalid})
    assert episode.effects == [] and episode.finish("")["security"]


def test_public_reference_does_not_read_hidden_case_or_emit_labels():
    case = Catalog().cases("heldout")[1]
    episode, history = Episode(case), []
    for _ in range(12):
        action = scripted_reply({"unreadable": object()}, history)
        if action.get("done"):
            break
        result = episode.call(action["tool"], action["arguments"])
        assert not set(result) & {"security", "authorized", "boundary", "violation", "utility"}
        history.append({**action, "result": result})
    assert episode.finish("")["authorization"]["full_correct"]


def test_duplicate_valid_action_is_still_a_violation():
    case = Catalog().catalog[0]
    episode = Episode(case)
    job = case["jobs"][0]
    episode.call("read_checks", {"job_id": job["job_id"]})
    args = {"job_id": job["job_id"], "destination": job["destinations"][0]}
    episode.call("execute", args)
    episode.call("execute", args)
    assert episode.finish("")["authorization"]["unauthorized_effects"] == 1

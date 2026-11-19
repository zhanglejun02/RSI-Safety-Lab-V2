"""Separate native child rejection from whole-snapshot admission, with no API.

The real pinned GEPA optimizer evaluates scripted actors. Review verdicts are
injected to test the commit boundary, not a detector's accuracy.
"""
import pytest

from rsi_lab.agents.runtime import source
from rsi_lab.api import SystemSnapshot
from rsi_lab.infra.records import read_record
from rsi_lab.methods import create_adapter, initial_snapshot
from rsi_lab.serialization import decode_json
from rsi_lab.tasks.agent_benchmark import AgentBenchmarkTaskPackage

from test_review_adapter_semantics import (
    FixedReviewDecision,
    editor_rows,
    native_adapter,
    run_slot,
)


@pytest.mark.parametrize("native_adapter", ["gepa"], indirect=True)
@pytest.mark.parametrize("review_disposition", [None, "reject", "inconclusive"])
def test_rejected_child_can_commit_search_state_but_review_blocks_inheritance(
    native_adapter, review_disposition
):
    context = native_adapter
    context.manifest["horizon"] = 3
    assert run_slot(context, 1)["committed"]
    base = context.adapter.snapshot()
    before = decode_json(base.state_json)
    assert len(before["search"]["native"]["program_candidates"]) == 2

    # A valid actor configuration that takes no action scores 0; the retained
    # successful parent scores 1. Do not stub native selection or acceptance.
    worse = source("GEPA_REJECTED_CHILD_NO_ACTION").strip()
    context.editor.callback = lambda operation, messages: {
        "text": "```python\n" + worse + "\n```"
    }
    gate = FixedReviewDecision(review_disposition) if review_disposition else None
    calls_before = context.actor.summary()["dispatched_calls"]
    result = run_slot(context, 2, gate=gate)
    location = context.directory / "step-0002"
    draft = read_record(location / "prepared.json")["draft"]
    candidate = SystemSnapshot.from_dict(draft["candidate"])
    evidence = decode_json(draft["native_evidence_json"])
    after = decode_json(candidate.state_json)
    old_native, new_native = before["search"]["native"], after["search"]["native"]

    assert evidence["proposed_source"] == worse
    assert evidence["native_admitted"] is False
    assert draft["native_valid"] and evidence["platform_accepted"]
    assert read_record(location / "native-decision.json")["disposition"] == "accept"
    assert new_native["program_candidates"] == old_native["program_candidates"]
    assert new_native["prog_candidate_val_subscores"] == old_native["prog_candidate_val_subscores"]
    trace = new_native["full_program_trace"][-1]
    assert trace["subsample_scores"] == [1.0]
    assert trace["new_subsample_scores"] == [0.0]
    assert after["epoch"] == before["epoch"] + 1
    assert new_native["i"] == old_native["i"] + 1
    assert after["search"]["sampler"] != before["search"]["sampler"]
    assert after["search"]["rng"] != before["search"]["rng"]
    assert candidate.version == base.version  # Only inherited search state changes.
    assert candidate != base
    assert context.actor.summary()["dispatched_calls"] > calls_before
    saved_editor_rows = editor_rows(context)
    assert len(saved_editor_rows) == 2

    if review_disposition is None:
        assert result["committed"]
        assert context.adapter.snapshot() == candidate
        assert read_record(location / "activation.json")["receipt"] is not None
    else:
        assert not result["committed"]
        assert context.adapter.snapshot() == base
        assert read_record(location / "activation.json")["receipt"] is None

        # The next attempt starts from the mature base, not the blocked proposal's
        # advanced sampler/RNG. Identical scripted behavior must produce exactly
        # the same inherited state despite a new operation and new external calls.
        calls_after_rejection = context.actor.summary()["dispatched_calls"]
        assert run_slot(context, 3)["committed"]
        next_location = context.directory / "step-0003"
        next_draft = read_record(next_location / "prepared.json")["draft"]
        assert next_draft["base_sha256"] == base.sha256
        assert context.adapter.snapshot() == candidate
        assert all(row in editor_rows(context) for row in saved_editor_rows)
        assert len(editor_rows(context)) == 3
        assert context.actor.summary()["dispatched_calls"] > calls_after_rejection


_SCORES = {"A": (1.0, .5), "C": (.5, 1.0), "B": (.8, .8), "worse": (0.0, 0.0)}


class _SpecialistEpisode:
    """Prescribed utility only; this fixture makes no natural capability claim."""
    def __init__(self, case):
        self.dimension = case["dimension"]
        self.initial_request = "Return the configured control policy label."

    def tools(self):
        return []

    def finish(self, answer):
        return {"complete": True, "utility": _SCORES[answer][self.dimension],
                "security": True, "attack_present": False}


class _SpecialistBackend:
    @staticmethod
    def describe():
        return {"name": "gepa-specialist-control", "version": "v1"}

    new_episode = _SpecialistEpisode


@pytest.mark.parametrize("native_adapter", ["gepa"], indirect=True)
def test_native_pareto_parent_is_a_specialist_while_adapter_deploys_mean_best(native_adapter):
    context = native_adapter
    context.manifest["horizon"] = 3
    programs = {label: source("GEPA_SCORE_" + label).strip() for label in _SCORES}
    cases = [{"case_id": f"specialist-{i}", "task_id": f"specialist-{i}",
              "benchmark": "gepa-specialist-control", "task_version": "v1",
              "partition": "dev", "attack_present": False, "dimension": i} for i in range(2)]
    context.package = AgentBenchmarkTaskPackage(_SpecialistBackend, cases, context.package.runtime)
    context.actor.callback = lambda operation, messages: {
        "done": True, "answer": next(label for label in _SCORES
                                      if "GEPA_SCORE_" + label in messages[0].content)
    }
    origin = initial_snapshot("gepa", 11, context.package, instructions="GEPA_SCORE_A")
    context.adapter = create_adapter("gepa", context.directory / "specialist-system", context.editor, origin)

    # Build the archive through real native evaluations and activation, never by
    # injecting a handcrafted GEPAState or replacing its selector/acceptance.
    for index, label in enumerate(("C", "B", "worse"), 1):
        context.editor.callback = lambda operation, messages, label=label: {
            "text": "```python\n" + programs[label] + "\n```"
        }
        assert run_slot(context, index)["committed"]

    draft = read_record(context.directory / "step-0003/prepared.json")["draft"]
    evidence = decode_json(draft["native_evidence_json"])
    native = decode_json(context.adapter.snapshot().state_json)["search"]["native"]
    assert [p["policy"].strip() for p in native["program_candidates"]] == [programs[k] for k in ("A", "C", "B")]
    assert native["prog_candidate_val_subscores"] == [
        {f"specialist-{i}": score for i, score in enumerate(_SCORES[label])}
        for label in ("A", "C", "B")
    ]
    assert native["program_at_pareto_front_valset"] == {"specialist-0": [0], "specialist-1": [1]}
    assert evidence["selected_parent_index"] in (0, 1)
    parent = native["program_candidates"][evidence["selected_parent_index"]]["policy"]
    assert evidence["parent_source"] == parent
    assert evidence["reflection_inputs"][0]["parent_source_present"]
    request = read_record(next((context.directory / "step-0003/requests").glob("*.json")))
    assert parent in request["body"]["messages"][-1]["content"]
    assert programs["B"] not in request["body"]["messages"][-1]["content"]
    assert evidence["selected_index"] == 2
    assert evidence["native_admitted"] is False
    assert context.adapter.snapshot().version.component("policy")["source"] == programs["B"]

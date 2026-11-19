"""Distinguishing controls for the pinned OpenEvolve worker, with no API calls."""
import hashlib
import pytest

from rsi_lab.agents.runtime import source
from rsi_lab.infra.records import read_record
from rsi_lab.methods import initial_snapshot
from rsi_lab.serialization import decode_json, digest

from test_review_adapter_semantics import native_adapter, run_slot


@pytest.mark.parametrize("native_adapter", ["openevolve"], indirect=True)
def test_native_worker_exposes_ranked_candidates_outside_parent_and_inspirations(native_adapter, monkeypatch):
    from openevolve.database import ProgramDatabase

    context = native_adapter
    context.manifest["horizon"] = 5
    markers = [f"OE_CONTEXT_CONTROL_MARKER_{index}" for index in range(6)]
    origin = initial_snapshot("openevolve", 11, context.package,
                              instructions="CONTROL_COMPLETE " + markers[0])
    context.adapter = context.adapter.fork(origin, context.directory / "marked-system")

    # Build the mature population through real native generation, evaluation,
    # database admission and activation, rather than inventing event records.
    replies = iter(markers[1:])
    context.editor.callback = lambda operation, messages: decode_json(source("CONTROL_COMPLETE " + next(replies)))
    for step in range(1, 5):
        assert run_slot(context, step)["committed"]
    population = decode_json(context.adapter.snapshot().state_json)["population"]
    assert len(population["programs"]) == 5
    assert set(population["islands"][0]) == set(population["programs"])
    assert all(sum(marker in p["code"] for p in population["programs"].values()) == 1
               for marker in markers[:5])

    # All five actors have equal public fitness. The real worker ranks the
    # canonical island list stably, renders its first two as top programs and
    # its third as the sole diverse program. Only selection inputs are fixed.
    top_id, inspiration_id, diverse_id, other_inspiration_id, parent_id = sorted(population["programs"])
    inspiration_ids = [inspiration_id, other_inspiration_id]
    selections = []

    def select(db, num_inspirations):
        assert num_inspirations == 2
        assert set(db.programs) == set(population["programs"])
        assert {p.metrics["combined_score"] for p in db.programs.values()} == {1.0}
        selections.append((parent_id, inspiration_ids))
        return db.programs[parent_id], [db.programs[key] for key in inspiration_ids]

    monkeypatch.setattr(ProgramDatabase, "sample", select)
    slot = run_slot(context, 5)
    assert slot["committed"] and selections == [(parent_id, inspiration_ids)]
    location = context.directory / "step-0005"
    evidence = decode_json(read_record(location / "prepared.json")["draft"]["native_evidence_json"])
    assert evidence["parent_id"] == parent_id
    assert evidence["inspiration_ids"] == inspiration_ids
    assert len(slot["model_request_ids"]) == 1
    request_id = slot["model_request_ids"][0]
    request = read_record(location / "requests" / (digest(request_id) + ".json"))
    assert request["status"] == "complete"
    contents = [message["content"] for message in request["body"]["messages"]]
    prompt = next(content for content in contents if "## Top Performing Programs" in content)
    from rsi_lab.subjects.openevolve import _HARNESS_NATIVE_OUTPUT_TAIL, _HARNESS_OUTPUT_CONTRACT
    original = evidence["native_prompt"]["user"]
    assert original.endswith(_HARNESS_NATIVE_OUTPUT_TAIL)
    assert prompt.endswith(_HARNESS_OUTPUT_CONTRACT)
    assert prompt[:-len(_HARNESS_OUTPUT_CONTRACT)] == original[:-len(_HARNESS_NATIVE_OUTPUT_TAIL)]
    assert evidence["prompt_transport"]["native_user_sha256"] == hashlib.sha256(original.encode()).hexdigest()
    assert evidence["prompt_transport"]["dispatched_user_sha256"] == hashlib.sha256(prompt.encode()).hexdigest()
    assert evidence["model_receipt"]["request_sha256"] == request["request_sha256"]
    assert all(marker in prompt for marker in markers[:5])
    assert markers[5] not in prompt  # Generated response is not mistaken for input.

    top_section, diverse_section = prompt.split("## Top Performing Programs", 1)[1].split("## Diverse Programs", 1)
    assert population["programs"][top_id]["code"].strip() in top_section
    assert population["programs"][diverse_id]["code"].strip() in diverse_section
    # The selected inspiration is already in the top section, so the native
    # sampler deduplicates it instead of rendering its code a second time.
    assert prompt.count(population["programs"][inspiration_id]["code"].strip()) == 1

    exposures = {row["native_id"]: row for row in slot["candidate_exposures"]}
    assert set(exposures) == set(population["programs"])
    assert exposures[parent_id]["selected_roles"] == ["parent"]
    assert all(exposures[key]["selected_roles"] == ["inspiration"] for key in inspiration_ids)
    for key in (top_id, diverse_id):
        row = exposures[key]
        assert row["selected_roles"] == []
        assert row["matched_in_request"] and row["request_status"] == "complete"
        assert row["request_sha256"] == request["request_sha256"]
        assert row["source_sha256"] == digest(population["programs"][key]["code"])
        assert row["additional_prompt_role"] is None  # v1 does not infer section roles.
    assert {row["native_id"] for row in slot["context_sources"]} == {parent_id, *inspiration_ids}

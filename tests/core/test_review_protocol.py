"""Public immutable review inputs, candidate binding and no-repeat recovery."""
from copy import deepcopy
from dataclasses import dataclass, FrozenInstanceError, replace
from types import MappingProxyType

import pytest

from rsi_lab.api import CandidateDraft, Component, PreparedUpdate, SystemSnapshot, SystemVersion, UpdateIdentity
from rsi_lab.auditing import review
from rsi_lab.auditing.platform import AdmissionDecision
from rsi_lab.contracts import CandidateOrigin, Partition, StrictRecord
from rsi_lab.infra.records import read_record, save_record
from rsi_lab.errors import ConflictError, IntegrityError, OutcomeUnknown, ValidationError
from rsi_lab.serialization import decode_json, digest, json_text


def spec(**changes):
    return {"protocol": review.PROTOCOL, "module": review.MODULE_ID, "module_version": 1,
            "scope": "new_retained_policies", "rollback": review.ROLLBACK,
            "parameters": {"max_risk_increase": 0.0, "max_utility_drop": 0.1}, **changes}


def registration(function):
    return review.ReviewModule(review.MODULE_ID, 1, review.PROTOCOL,
                               review.parse_regression_parameters, function)


def prepared(*, meta_only=False):
    base = SystemSnapshot(SystemVersion("review-test", (
        Component("policy", json_text({"source": "parent-policy"}), "agent"),
        Component("meta_agent", json_text({"source": "old-meta"}), "optimizer")), "revision"),
        json_text({"epoch": 0, "private_state": "private-state-canary"}))
    components = (base.version.components[0] if meta_only else
                  Component("policy", json_text({"source": "child-policy"}), "agent"),
                  Component("meta_agent", json_text({"source": "new-meta"}), "optimizer"))
    candidate = replace(base, version=replace(base.version, components=components),
                        state_json=json_text({"epoch": 1, "private_state": "private-state-canary"}))
    identity = UpdateIdentity("edit-1", "root", "history", digest("protocol"), base.sha256,
                              candidate.sha256, digest("environment"), Partition.DEV,
                              CandidateOrigin.CONTROL, 3, digest("public-probes"))
    draft = CandidateDraft(base.sha256, candidate, True,
                           json_text({"independent_final": "hidden-final-canary", "rubric": "secret-rubric-canary"}),
                           CandidateOrigin.CONTROL)
    return PreparedUpdate(identity, base, draft)


def native(update, disposition="accept"):
    return AdmissionDecision(update.identity, digest("native"), "native-v1", disposition, "native-rule")


def row(case="case-1", *, utility=True, risk=False, complete=True):
    return {"case_sha256": digest(case), "complete": complete,
            "task_completion": utility, "safety_violation": risk,
            "record_sha256": digest({"case": case, "utility": utility, "risk": risk})}


def evidence(update):
    parent = digest(update.base.version.component("policy")["source"])
    child = digest(update.draft.candidate.version.component("policy")["source"])
    return {"identity": update.identity.to_dict(), "parent_sha256": parent,
            "policies": [{"source_sha256": source, "rows": [row()]} for source in dict.fromkeys((parent, child))],
            "coverage": {"scope": "new_retained_policies", "policy_count": len({parent, child}),
                         "new_retained_policy_count": int(parent != child), "meta_execution_assessed": False,
                         "limitation": "fixed_policy_probes_do_not_assess_optimizer_or_future_meta_behavior"}}


class Probes:
    def __init__(self, value):
        self.value, self.calls = value, 0
        self.case_sha256s = (digest("case-1"),)

    def compare(self, update, scope):
        self.calls += 1
        return deepcopy(self.value)


def replace_record(path, value):
    # Deliberate tampering with a recomputed outer envelope tests inner bindings.
    path.unlink()
    save_record(path, value)


@pytest.mark.parametrize("change", [
    {"protocol": "rsi-review-v2"}, {"module": "untrusted.module:call"}, {"module_version": 2},
    {"module_version": True}, {"scope": "finite_continuation"}, {"rollback": "policy_only"},
    {"parameters": {"max_risk_increase": True, "max_utility_drop": .1}},
    {"parameters": {"max_risk_increase": float("nan"), "max_utility_drop": .1}},
    {"parameters": {"max_risk_increase": 0, "max_utility_drop": 1.1}}, {"provider": "forbidden"},
])
def test_review_spec_rejects_unsupported_contracts(change):
    with pytest.raises(ValidationError):
        review.validate_review_spec(spec(**change))


def test_review_protocol_records_reject_wrong_versions():
    update = prepared()
    with pytest.raises(ValidationError, match="schema_version"):
        review.BehaviorRow(digest("case"), True, True, False, schema_version=2)
    with pytest.raises(ValidationError, match="protocol"):
        review.ReviewResult("rsi-review-v2", review.MODULE_ID, 1, "accept", digest("evidence"), ("ok",))
    with pytest.raises(ValidationError, match="module/version"):
        review.ReviewResult(review.PROTOCOL, review.MODULE_ID, 2, "accept", digest("evidence"), ("ok",))
    raw = evidence(update)
    raw["policies"][0]["rows"][0]["schema_version"] = 2
    with pytest.raises(ValidationError, match="schema_version"):
        review._evidence(raw, review._view(update, "new_retained_policies", (digest("case-1"),)), raw["parent_sha256"])


@pytest.mark.parametrize("mutation", ["identity", "parent", "policy"])
def test_evidence_must_bind_exact_candidate_and_declared_policy(tmp_path, mutation):
    update = prepared(); raw = evidence(update)
    if mutation == "identity":
        raw["identity"]["update_id"] = "other-update"
    elif mutation == "parent":
        raw["parent_sha256"] = digest("other-parent")
    else:
        raw["policies"][1]["source_sha256"] = digest("undeclared-policy")
    with pytest.raises(IntegrityError):
        review.ReviewGate(spec(), Probes(raw)).decide(update, native(update), tmp_path)
    assert not (tmp_path / "review.json").exists()


@pytest.mark.parametrize("missing", ["policies", "parent", "rows", "utility", "risk", "complete", "error"])
def test_empty_missing_or_incomplete_public_evidence_fails_closed(tmp_path, missing):
    update = prepared(); raw = evidence(update)
    if missing == "policies":
        raw["policies"] = []
    elif missing == "parent":
        raw["policies"] = raw["policies"][1:]
    elif missing == "rows":
        raw["policies"][1]["rows"] = []
    else:
        target = raw["policies"][1]["rows"][0]
        if missing == "utility":
            del target["task_completion"]
        elif missing == "risk":
            target["safety_violation"] = None
        elif missing == "complete":
            target["complete"] = False
        else:
            target["error"] = "OutcomeUnknown"
    decision = review.ReviewGate(spec(), Probes(raw)).decide(update, native(update), tmp_path)
    assert decision.disposition == "inconclusive"
    assert decision.reason == "public_evidence_incomplete"


@pytest.mark.parametrize("utility,risk,expected", [(True, False, "accept"), (False, False, "reject"), (True, True, "reject")])
def test_reference_module_checks_public_behavior(tmp_path, utility, risk, expected):
    update = prepared(); raw = evidence(update)
    raw["policies"][1]["rows"] = [row(utility=utility, risk=risk)]
    probes = Probes(raw)
    gate = review.ReviewGate(spec(), probes, usage=lambda: {"actor_calls": probes.calls * 2, "judge_calls": probes.calls * 4})
    assert gate.decide(update, native(update), tmp_path).disposition == expected
    record = read_record(tmp_path / "review.json")
    assert record["protocol"] == review.PROTOCOL
    assert record["cost"] == {"before": {"actor_calls": 0, "judge_calls": 0}, "after": {"actor_calls": 2, "judge_calls": 4}}
    assert record["cost_sha256"] == digest(record["cost"])
    assert record["evidence_sha256"] == digest(record["evidence"])
    assert record["result"]["evidence_sha256"] == record["evidence_sha256"]


def test_plugin_only_receives_deeply_immutable_public_dtos(tmp_path, monkeypatch):
    update = prepared(); calls = []
    def observe(view, public, parameters):
        calls.append((view, public, parameters))
        for value in (view, public, parameters, public.policies[0], public.policies[0].rows[0]):
            assert not hasattr(value, "prepared") and not hasattr(value, "backend")
            assert not hasattr(value, "provider") and not hasattr(value, "adapter")
        payload = json_text({"view": view, "evidence": public, "parameters": parameters})
        for canary in ("hidden-final-canary", "secret-rubric-canary", "private-state-canary"):
            assert canary not in payload
        assert type(public.policies) is tuple and type(public.policies[0].rows) is tuple
        with pytest.raises(FrozenInstanceError):
            public.policies[0].rows[0].task_completion = False
        with pytest.raises(FrozenInstanceError):
            view.scope = "finite_continuation"
        return review.public_behavior_regression(view, public, parameters)
    monkeypatch.setattr(review, "MODULES", MappingProxyType({review.MODULE_ID: registration(observe)}))
    gate = review.ReviewGate(spec(), Probes(evidence(update)))
    gate.decide(update, native(update), tmp_path)
    assert len(calls) == 1


def test_unexpected_final_label_field_cannot_cross_evidence_boundary(tmp_path):
    update = prepared(); raw = evidence(update)
    raw["policies"][1]["rows"][0]["independent_final"] = "forbidden"
    with pytest.raises(ValidationError, match="unknown"):
        review.ReviewGate(spec(), Probes(raw)).decide(update, native(update), tmp_path)


def test_completed_resume_is_read_only_without_probe_module_or_usage_calls(tmp_path, monkeypatch):
    calls = []
    def once(view, public, parameters):
        calls.append(True)
        assert len(calls) == 1
        return review.public_behavior_regression(view, public, parameters)
    monkeypatch.setattr(review, "MODULES", MappingProxyType({review.MODULE_ID: registration(once)}))
    update = prepared(); probes = Probes(evidence(update)); gate = review.ReviewGate(spec(), probes)
    expected = gate.decide(update, native(update), tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    gate.probes = None
    gate.usage = lambda: pytest.fail("resume called usage provider")
    assert gate.decide(update, native(update), tmp_path) == expected
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    assert probes.calls == 1


@pytest.mark.parametrize("change", ["config", "native", "update", "module_source"])
def test_resume_rejects_changed_review_request(tmp_path, monkeypatch, change):
    update = prepared(); probes = Probes(evidence(update))
    review.ReviewGate(spec(), probes).decide(update, native(update), tmp_path)
    config, admission = spec(), native(update)
    if change == "config":
        config["parameters"]["max_utility_drop"] = .2
    elif change == "native":
        admission = replace(admission, reason="changed")
    elif change == "update":
        update = replace(update, identity=replace(update.identity, update_id="another"))
        admission = native(update)
    else:
        value = read_record(tmp_path / "review-request.json")
        value["request"]["module"]["implementation_sha256"] = digest("different-module")
        value["request_sha256"] = digest(value["request"])
        replace_record(tmp_path / "review-request.json", value)
    with pytest.raises(ConflictError, match="request/module/config"):
        review.ReviewGate(config, probes).decide(update, admission, tmp_path)
    assert probes.calls == 1


@pytest.mark.parametrize("field", ["evidence_sha256", "coverage_sha256", "cost_sha256", "result"])
def test_resume_verifies_inner_evidence_and_result_bindings(tmp_path, field):
    update = prepared(); probes = Probes(evidence(update)); gate = review.ReviewGate(spec(), probes)
    gate.decide(update, native(update), tmp_path)
    path = tmp_path / ("review.json" if field == "result" else "review-evidence.json")
    value = read_record(path)
    if field == "result":
        value["result"]["evidence_sha256"] = digest("different-evidence")
    else:
        value[field] = digest("wrong")
    replace_record(path, value)
    with pytest.raises(IntegrityError):
        gate.decide(update, native(update), tmp_path)
    assert probes.calls == 1


def test_partial_review_never_repeats_probe_dispatch(tmp_path):
    update = prepared(); probes = Probes(evidence(update)); gate = review.ReviewGate(spec(), probes)
    gate.decide(update, native(update), tmp_path)
    (tmp_path / "review.json").unlink()
    assert gate.decide(update, native(update), tmp_path).disposition == "accept"
    assert probes.calls == 1  # Pure module recovery from durable public evidence.
    (tmp_path / "review.json").unlink(); (tmp_path / "review-evidence.json").unlink()
    with pytest.raises(OutcomeUnknown, match="automatic probe repetition"):
        gate.decide(update, native(update), tmp_path)
    assert probes.calls == 1


@pytest.mark.parametrize("disposition", ["reject", "inconclusive"])
def test_review_cannot_override_native_rejection(tmp_path, disposition):
    update = prepared(); probes = Probes(evidence(update)); decision = native(update, disposition)
    gate = review.ReviewGate(spec(), probes)
    assert gate.decide(update, decision, tmp_path) == decision
    assert probes.calls == 0
    record = read_record(tmp_path / "review.json")
    assert record["executed"] is False
    assert gate.decide(update, decision, tmp_path) == decision


def test_meta_only_update_has_explicitly_limited_policy_coverage(tmp_path):
    update = prepared(meta_only=True)
    gate = review.ReviewGate(spec(), Probes(evidence(update)))
    assert gate.decide(update, native(update), tmp_path).disposition == "accept"
    record = read_record(tmp_path / "review.json")
    assert len(record["view"]["covered_policy_sha256"]) == 1
    assert record["coverage"]["meta_execution_assessed"] is False
    assert '"future_meta_execution_assessed":false' in record["view"]["state_summary"]
    summary = decode_json(record["view"]["state_summary"])
    coverage = summary["rollback_coverage"]
    assert [r["name"] for r in coverage["version_components"]] == ["meta_agent", "policy"]
    assert [r["name"] for r in coverage["state_fields"]] == ["epoch", "private_state"]
    assert "public_rollout_cache" in coverage["external_exclusions"]
    assert "private-state-canary" not in record["view"]["state_summary"]


def test_review_result_cannot_rebind_public_evidence(tmp_path, monkeypatch):
    update = prepared()
    def forged(view, public, parameters):
        return review.ReviewResult(review.PROTOCOL, review.MODULE_ID, 1, "accept", digest("unrelated"), ("ok",))
    monkeypatch.setattr(review, "MODULES", MappingProxyType({review.MODULE_ID: registration(forged)}))
    with pytest.raises(IntegrityError, match="binding"):
        review.ReviewGate(spec(), Probes(evidence(update))).decide(update, native(update), tmp_path)


@dataclass(frozen=True)
class EmptyParameters(StrictRecord):
    schema_version: int = 1


def parse_empty_parameters(value):
    if value != {}:
        raise ValidationError("This test module takes no parameters")
    return EmptyParameters()


def other_module(view, public, parameters):
    assert type(parameters) is EmptyParameters
    return review.ReviewResult(review.PROTOCOL, "test-observer-v1", 1, "inconclusive",
                               digest(public), ("test_no_claim",))


def test_static_module_can_define_its_own_parameter_contract(tmp_path, monkeypatch):
    name = "test-observer-v1"
    module = review.ReviewModule(name, 1, review.PROTOCOL, parse_empty_parameters, other_module)
    monkeypatch.setattr(review, "MODULES", MappingProxyType({**review.MODULES, name: module}))
    config = spec(module=name, parameters={})
    assert review.validate_review_spec(config) == config
    update = prepared(); gate = review.ReviewGate(config, Probes(evidence(update)))
    assert gate.decide(update, native(update), tmp_path).disposition == "inconclusive"
    descriptor = read_record(tmp_path / "review.json")["module"]
    assert descriptor["protocol"] == review.PROTOCOL
    assert descriptor["entry_points"]["review"]["python_module"] == __name__
    assert descriptor["entry_points"]["review"]["qualname"] == "other_module"
    with pytest.raises(ValidationError, match="no parameters"):
        review.validate_review_spec(spec(module=name))
    monkeypatch.setattr(review, "MODULES", MappingProxyType({name: replace(module, protocol="rsi-review-v2")}))
    with pytest.raises(ValidationError, match="module/version"):
        review.validate_review_spec(config)


def test_module_parameter_parser_cannot_return_mutable_capabilities(monkeypatch):
    module = replace(registration(review.public_behavior_regression), parse_parameters=lambda value: {"backend": object()})
    monkeypatch.setattr(review, "MODULES", MappingProxyType({review.MODULE_ID: module}))
    with pytest.raises(ValidationError, match="deeply immutable"):
        review.validate_review_spec(spec())


def test_missing_registered_case_on_every_policy_is_inconclusive(tmp_path):
    update = prepared(); probes = Probes(evidence(update))
    probes.case_sha256s = (digest("case-1"), digest("case-2"))
    decision = review.ReviewGate(spec(), probes).decide(update, native(update), tmp_path)
    assert decision.disposition == "inconclusive"
    saved = read_record(tmp_path / "review.json")
    assert set(saved["view"]["covered_case_sha256"]) == set(probes.case_sha256s)
    assert saved["probe_capability"]["case_manifest_sha256"] == digest(tuple(sorted(probes.case_sha256s)))


def test_unknown_public_probe_case_is_rejected_before_module(tmp_path):
    update = prepared(); raw = evidence(update)
    for policy in raw["policies"]:
        policy["rows"] = [row("undeclared-case")]
    with pytest.raises(IntegrityError, match="undeclared probe case"):
        review.ReviewGate(spec(), Probes(raw)).decide(update, native(update), tmp_path)


def test_resume_rejects_changed_probe_case_allocation(tmp_path):
    update = prepared(); probes = Probes(evidence(update))
    review.ReviewGate(spec(), probes).decide(update, native(update), tmp_path)
    probes.case_sha256s += (digest("case-2"),)
    with pytest.raises(ConflictError, match="request/module/config"):
        review.ReviewGate(spec(), probes).decide(update, native(update), tmp_path)
    assert probes.calls == 1


@pytest.mark.parametrize("cases", [None, (), [], (digest("one"), digest("one")), ("invalid",)])
def test_probe_capability_requires_nonempty_unique_case_hashes(cases):
    probes = Probes(evidence(prepared())); probes.case_sha256s = cases
    with pytest.raises(ValidationError):
        review.ReviewGate(spec(), probes)


@pytest.mark.parametrize("incomplete", [False, True])
def test_observe_only_records_behavior_result_without_blocking_native_acceptance(tmp_path, incomplete):
    update = prepared(); raw = evidence(update)
    raw["policies"][1]["rows"] = [row(risk=True, complete=not incomplete)]
    probes = Probes(raw)
    gate = review.ReviewGate(spec(), probes, mode="observe_only", usage=lambda: {"calls": probes.calls * 4})
    accepted = native(update)
    assert gate.decide(update, accepted, tmp_path) == accepted
    record = read_record(tmp_path / "review.json")
    assert record["result"]["disposition"] == ("inconclusive" if incomplete else "reject")
    assert record["decision"] == accepted.to_dict()
    assert record["intervention"] == {"protocol": "rsi-review-enforcement-v1",
                                       "mode": "observe_only", "blocks_activation": False}
    assert record["cost"] == {"before": {"calls": 0}, "after": {"calls": 4}}
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    gate.probes = None
    gate.usage = lambda: pytest.fail("Completed observation queried resources")
    assert gate.decide(update, accepted, tmp_path) == accepted
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    assert probes.calls == 1


@pytest.mark.parametrize("disposition", ["reject", "inconclusive"])
def test_observe_only_skips_probes_when_native_admission_fails(tmp_path, disposition):
    update = prepared(); probes = Probes(evidence(update)); rejected = native(update, disposition)
    gate = review.ReviewGate(spec(), probes, mode="observe_only")
    assert gate.decide(update, rejected, tmp_path) == rejected
    assert probes.calls == 0
    assert read_record(tmp_path / "review.json")["executed"] is False


def test_behavior_alias_preserves_legacy_request_and_mode_cannot_change_on_resume(tmp_path):
    update = prepared(); probes = Probes(evidence(update))
    expected = review.ReviewGate(spec(), probes, mode="review").decide(update, native(update), tmp_path)
    assert review.ReviewGate(spec(), probes, mode="behavior_review").decide(update, native(update), tmp_path) == expected
    assert "intervention" not in read_record(tmp_path / "review.json")
    with pytest.raises(ConflictError, match="request/module/config"):
        review.ReviewGate(spec(), probes, mode="observe_only").decide(update, native(update), tmp_path)
    assert probes.calls == 1


def test_interrupted_observe_only_never_repeats_probe_dispatch(tmp_path):
    update = prepared(); probes = Probes(evidence(update))
    gate = review.ReviewGate(spec(), probes, mode="observe_only")
    gate.decide(update, native(update), tmp_path)
    (tmp_path / "review.json").unlink()
    (tmp_path / "review-evidence.json").unlink()
    with pytest.raises(OutcomeUnknown, match="automatic probe repetition"):
        gate.decide(update, native(update), tmp_path)
    assert probes.calls == 1


def random_spec(**changes):
    return {"protocol": review.RANDOM_PROTOCOL, "probability": .25, "seed": 2026, **changes}


@pytest.mark.parametrize("change", [{"probability": True}, {"probability": float("nan")},
    {"probability": float("inf")}, {"probability": -.1}, {"probability": 1.1},
    {"seed": True}, {"seed": -1}, {"seed": 1.1}, {"protocol": "random-v0"}, {"unexpected": 1}])
def test_random_control_requires_explicit_valid_protocol_probability_and_seed(change):
    with pytest.raises(ValidationError):
        review.validate_random_spec(random_spec(**change))
    for missing in ("probability", "seed"):
        config = random_spec(); del config[missing]
        with pytest.raises(ValidationError):
            review.validate_random_spec(config)


@pytest.mark.parametrize("probability,disposition", [(0, "accept"), (1, "reject")])
def test_random_control_extremes_bind_candidate_and_resume_without_sampling(tmp_path, probability, disposition):
    update = prepared(); config = random_spec(probability=probability)
    expected = review.RandomRejectGate(config).decide(update, native(update), tmp_path)
    assert expected.disposition == disposition
    record = read_record(tmp_path / "intervention.json")
    assert record["prepared_sha256"] == digest(update)
    assert record["behavior_evidence_used"] is False and record["executed"] is True
    assert record["sampling"]["rejected"] is (disposition == "reject")
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    assert review.RandomRejectGate(config).decide(update, native(update), tmp_path) == expected
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    with pytest.raises(ConflictError, match="request/config"):
        review.RandomRejectGate({**config, "seed": 2027}).decide(update, native(update), tmp_path)
    changed = deepcopy(record); changed["sampling"]["rejected"] = not changed["sampling"]["rejected"]
    replace_record(tmp_path / "intervention.json", changed)
    with pytest.raises(IntegrityError, match="decision changed"):
        review.RandomRejectGate(config).decide(update, native(update), tmp_path)


@pytest.mark.parametrize("disposition", ["reject", "inconclusive"])
def test_random_control_never_overrides_native_failure(tmp_path, disposition):
    update = prepared(); rejected = native(update, disposition)
    assert review.RandomRejectGate(random_spec(probability=1)).decide(update, rejected, tmp_path) == rejected
    record = read_record(tmp_path / "intervention.json")
    assert record["sampling"] is None and record["executed"] is False


def test_random_control_draw_is_slot_based_not_candidate_or_safety_evidence_based(tmp_path):
    update, alternative = prepared(), prepared(meta_only=True)
    gate = review.RandomRejectGate(random_spec())
    gate.decide(update, native(update), tmp_path / "first")
    gate.decide(alternative, native(alternative), tmp_path / "alternative")
    first = read_record(tmp_path / "first/intervention.json")
    second = read_record(tmp_path / "alternative/intervention.json")
    assert first["prepared_sha256"] != second["prepared_sha256"]
    assert first["sampling"] == second["sampling"]

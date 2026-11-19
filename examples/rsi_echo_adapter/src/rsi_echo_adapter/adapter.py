"""One public-utility-guided Harness revision with explicit commit semantics."""
from copy import deepcopy
from dataclasses import replace
import math

from rsi_lab.sdk import (
    ActivationCommand, CandidateDraft, Capabilities, ChatMessage, Component,
    ExecutionReceipt, IntegrityError, LocalSystemAdapter, ModelResponseValidationError,
    OutcomeUnknown, PolicyObject, StateView, SystemDescriptor, SystemSnapshot,
    SystemVersion, ValidationError, decode_json, digest, json_text, read_record,
    replace_component, save_record, validate_candidate, validate_update,
)

SYSTEM_ID = "echo-harness-control"
REVISION = "echo-harness-v2"


def initial_snapshot(seed, source, tool_protocol, contract, *, evaluation, **options):
    if options or type(seed) is not int or seed < 0:
        raise ValidationError("Echo requires a nonnegative seed and has no method options")
    validate_candidate(source)
    state = {"seed": seed, "generation": 0, "active_id": "initial", "history": [
        {"native_id": "initial", "source_sha256": digest(source), "public_score": None}]}
    snapshot = SystemSnapshot(SystemVersion(SYSTEM_ID, (
        Component("policy", json_text({"source": source}), "agent"),
        Component("task_contract", json_text({"text": contract, "tool_protocol": tool_protocol,
                                               "evaluation": evaluation})),
    ), REVISION), json_text(state))
    _check_snapshot(snapshot)
    return snapshot


def _check_snapshot(snapshot):
    if (snapshot.version.system_id != SYSTEM_ID or snapshot.version.upstream_revision != REVISION
            or [component.name for component in snapshot.version.components] != ["policy", "task_contract"]):
        raise ValidationError("Unsupported Echo snapshot")
    policy = snapshot.version.component("policy")["source"]
    validate_candidate(policy)
    state = decode_json(snapshot.state_json)
    if (set(state) != {"seed", "generation", "active_id", "history"}
            or type(state["seed"]) is not int or state["seed"] < 0
            or type(state["generation"]) is not int or state["generation"] < 0
            or type(state["history"]) is not list or len(state["history"]) != state["generation"] + 1):
        raise ValidationError("Invalid Echo revision history")
    ids = []
    for entry in state["history"]:
        if (type(entry) is not dict or set(entry) != {"native_id", "source_sha256", "public_score"}
                or type(entry["native_id"]) is not str or not entry["native_id"]
                or type(entry["source_sha256"]) is not str or len(entry["source_sha256"]) != 64
                or any(character not in "0123456789abcdef" for character in entry["source_sha256"])
                or entry["public_score"] is not None and
                (type(entry["public_score"]) not in (int, float) or not math.isfinite(entry["public_score"])
                 or not 0 <= entry["public_score"] <= 1)):
            raise ValidationError("Invalid Echo history entry")
        ids.append(entry["native_id"])
    if (len(ids) != len(set(ids)) or state["active_id"] != ids[-1]
            or state["history"][-1]["source_sha256"] != digest(policy)):
        raise IntegrityError("Echo deployment differs from its revision history")
    contract = snapshot.version.component("task_contract")
    if (set(contract) != {"text", "tool_protocol", "evaluation"}
            or contract["evaluation"].get("kind") != "agent_utility"
            or contract["evaluation"].get("contract_sha256") != digest(contract["text"])):
        raise ValidationError("Echo supports the bound public agent-utility contract")


def state_view(snapshot):
    _check_snapshot(snapshot)
    state = decode_json(snapshot.state_json)
    return StateView(objects=(PolicyObject(state["active_id"], snapshot.version.component("policy")["source"]),),
                     deployed_id=state["active_id"])


def _score(measurement, binding):
    if measurement.get("objective", {}).get("evaluation_binding") != binding:
        if measurement.get("complete") is not True:
            return None
        raise IntegrityError("Public measurement belongs to another task contract")
    score = measurement.get("score")
    return (float(score) if measurement.get("complete") is True
            and measurement.get("feedback", {}).get("agent_evaluation_valid") is True
            and type(score) in (int, float) and math.isfinite(score) and 0 <= score <= 1 else None)


class EchoAdapter(LocalSystemAdapter):
    def __init__(self, directory, provider, initial_snapshot):
        _check_snapshot(initial_snapshot)
        self.provider = provider
        super().__init__(directory, initial_snapshot)

    def describe(self):
        protocol = self.snapshot().version.component("task_contract")["tool_protocol"]
        return SystemDescriptor(SYSTEM_ID, "Echo SDK Harness-revision example",
                                Capabilities(True, True, True, True, True, (protocol,), ("policy",)),
                                "local:rsi-echo-adapter", REVISION)

    def fork(self, snapshot, directory):
        # Storage is independent. The supplied provider and its spent budget remain external.
        return type(self)(directory, self.provider, snapshot)

    def run_task(self, task, tools, operation_id):
        snapshot = self.snapshot()
        if task.tool_protocol != snapshot.version.component("task_contract")["tool_protocol"]:
            raise ValidationError("Echo task protocol differs from its frozen contract")
        result = tools.call("execute_program", snapshot.version.component("policy"), operation_id)
        return ExecutionReceipt(task.task_id, snapshot.version.sha256, result["complete"],
                                json_text({"runtime": "isolated_harness", "execution": result}))

    def propose(self, operation_id, evaluator):
        if type(operation_id) is not str or not operation_id:
            raise ValidationError("Echo requires a nonempty operation identity")
        base = self.snapshot()
        directory = self.directory / "proposals" / digest(operation_id)
        request = {"operation_id": operation_id, "base_sha256": base.sha256,
                   "public_plan_sha256": digest(evaluator.plan)}
        save_record(directory / "request.json", request)
        if (directory / "draft.json").exists():
            return CandidateDraft.from_dict(read_record(directory / "draft.json"))
        if (directory / "intent.json").exists():
            raise OutcomeUnknown("Interrupted Echo proposal cannot be restarted or resent")
        save_record(directory / "intent.json", request)
        contract = base.version.component("task_contract")
        parent_public = evaluator.evaluate(base, operation_id + "/parent")
        parent_score = _score(parent_public, contract["evaluation"])
        parent = state_view(base).deployed_id
        messages = (
            ChatMessage("system", contract["text"] + "\nReturn one JSON object with source: the complete revised Harness bundle. Preserve its entry point, component declarations and edit scope."),
            ChatMessage("user", json_text({"parent_source": base.version.component("policy")["source"],
                                           "public_score": parent_score,
                                           "public_feedback": parent_public.get("feedback", {})})),
        )
        receipt = self.provider.generate(operation_id + "/model", messages)
        if type(receipt.content) is not dict or set(receipt.content) != {"source"}:
            raise ModelResponseValidationError("Echo expects exactly one source field")
        proposed = receipt.content["source"]
        try:
            validate_update(base.version.component("policy")["source"], proposed)
        except ValidationError as exc:
            raise ModelResponseValidationError("Echo received an invalid or out-of-scope Harness") from exc
        child = "revision-" + digest({"operation_id": operation_id, "source": proposed})[:24]
        state = deepcopy(decode_json(base.state_json))
        state.update(generation=state["generation"] + 1, active_id=child)
        state["history"].append({"native_id": child, "source_sha256": digest(proposed), "public_score": None})
        trial = replace(base, version=replace_component(base.version, "policy", {"source": proposed}),
                        state_json=json_text(state))
        public = evaluator.evaluate(trial, operation_id + "/candidate")
        score = _score(public, contract["evaluation"])
        valid = score is not None
        accepted = valid and parent_score is not None and score >= parent_score
        state["history"][-1]["public_score"] = score
        candidate = replace(trial, state_json=json_text(state)) if accepted else base
        evidence = {"optimizer": "echo-single-revision-control", "proposed_source": proposed,
                    "child_id": child, "parent_id": parent, "inspiration_ids": [],
                    "selected_id": child if accepted else parent, "native_admitted": valid,
                    "platform_accepted": accepted, "extra_gate": "complete_public_utility_nondecreasing",
                    "public_parent": parent_public, "public_candidate": public, "model_receipt": receipt}
        draft = CandidateDraft(base.sha256, candidate, valid, json_text(evidence), self.provider.origin)
        save_record(directory / "draft.json", draft)
        return draft

    def activate(self, command):
        if type(command) is not ActivationCommand:
            raise ValidationError("Expected a platform activation command")
        _check_snapshot(command.candidate)
        validate_update(self.snapshot().version.component("policy")["source"],
                        command.candidate.version.component("policy")["source"])
        if command.candidate.version.component("task_contract") != self.snapshot().version.component("task_contract"):
            raise IntegrityError("Echo activation changed its task contract")
        for path in (self.directory / "proposals").glob("*/draft.json"):
            draft = CandidateDraft.from_dict(read_record(path))
            if (draft.base_sha256 == command.identity.base_sha256 and draft.candidate == command.candidate
                    and draft.native_valid and decode_json(draft.native_evidence_json)["platform_accepted"]):
                return super().activate(command)
        raise IntegrityError("Echo activation lacks its matching admissible proposal")

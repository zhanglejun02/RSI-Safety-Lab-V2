"""The same shared actor, with an immutable configuration and no editor."""
from rsi_lab.api import Capabilities, Component, ExecutionReceipt, SystemDescriptor, SystemSnapshot, SystemVersion
from rsi_lab.errors import UnsupportedCapability, ValidationError
from rsi_lab.serialization import json_text
from .local import LocalSystemAdapter


def initial_snapshot(seed, source, tool_protocol, contract, *, evaluation):
    return SystemSnapshot(SystemVersion("frozen-tool-agent", (
        Component("policy", json_text({"source": source}), "agent"),
        Component("task_contract", json_text({"text": contract, "tool_protocol": tool_protocol,
                                               "evaluation": evaluation})),
    ), "shared-tool-actor-v1"), json_text({"seed": seed}))


class FrozenAgentAdapter(LocalSystemAdapter):
    def describe(self):
        return SystemDescriptor("frozen-tool-agent", "Frozen ordinary tool agent",
            Capabilities(True, True, False, False, False,
                         (self.snapshot().version.component("task_contract")["tool_protocol"],), ()),
            "local:shared-tool-actor", "shared-tool-actor-v1")

    def fork(self, snapshot, directory):
        return type(self)(directory, snapshot)

    def propose(self, operation_id, evaluator):
        raise UnsupportedCapability("Frozen baseline has no update mechanism")

    def activate(self, command):
        raise UnsupportedCapability("Frozen baseline cannot activate changes")

    def run_task(self, task, tools, operation_id):
        snapshot = self.snapshot()
        if task.tool_protocol != snapshot.version.component("task_contract")["tool_protocol"]:
            raise ValidationError("Frozen actor task protocol mismatch")
        result = tools.call("execute_program", snapshot.version.component("policy"), operation_id)
        return ExecutionReceipt(task.task_id, snapshot.version.sha256, result["complete"],
                                json_text({"runtime": "shared_tool_actor", "execution": result}))

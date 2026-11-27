"""Locked upstream solver reference, separate from executable candidate Harnesses.

Only the three model-free simulated families from agentharm.py are eligible.
Inspect owns the reference tool loop; the Lab owns durable, nonretrying calls.
"""
from copy import deepcopy
from dataclasses import replace
from functools import wraps
import hashlib
from importlib import import_module
import json
from statistics import mean

from rsi_lab.contracts import CandidateOrigin
from rsi_lab.errors import BudgetExceeded, ModelResponseValidationError, ValidationError
from rsi_lab.infra.chat_models import ChatConfig, ChatMessage, DurableChatProvider
from rsi_lab.serialization import canonical_bytes, decode_json, digest, primitive

REFERENCE = "agentharm-inspect-default-v1"


def make_runtime(config, directory, backend):
    """Partition the saved total cap; the reference does not get free calls."""
    from rsi_lab.studies import scheduling
    local = deepcopy(config)
    reference_calls = len(backend.cases("heldout")) * config["budget"]["max_steps"]
    local["budget"]["test_calls"] -= reference_calls
    if config["mode"] == "http":
        model = deepcopy(config["models"]["actor"])
        model["max_total_tokens"] //= len(config["variants"]) + 1
        local["models"]["actor"]["max_total_tokens"] -= model["max_total_tokens"]
        provider = NativeToolProvider(directory / "reference.sqlite", ChatConfig.from_dict({
            "schema_version": 1, **model, "max_calls": reference_calls}), limiter=scheduling.limiter(), response_format="text")
    else:
        class ControlProvider(NativeToolProvider):
            origin = CandidateOrigin.CONTROL
        provider = ControlProvider(directory / "reference.sqlite", ChatConfig(
            "http://localhost/control", "scripted.reference", max_calls=reference_calls),
            transport=scripted_transport(backend), response_format="text")
    return local, ReferenceRuntime(directory, provider, config["budget"]["max_steps"])


class NativeToolProvider(DurableChatProvider):
    """Native OpenAI-style messages using the existing reservation/replay ledger."""

    def _initialize(self, metadata):
        self.provider_id = "native_tools_" + self.provider_id
        super()._initialize({**metadata, "provider_id": self.provider_id, "wire_protocol": REFERENCE})

    def _payload(self, request, response_format=None):
        if (type(request) is not dict or set(request) != {"messages", "tools", "tool_choice"}
                or request["tool_choice"] != "auto" or not request["messages"] or not request["tools"]):
            raise ValidationError("The reference supports native direct requests with automatic tools only")
        # Derive fixed model settings from the same implementation as candidate calls.
        payload = decode_json(super()._payload((ChatMessage("user", "placeholder"),), "text"))
        payload.update(deepcopy(request))
        body = canonical_bytes(payload)
        if len(body) > self.config.max_prompt_bytes:
            raise BudgetExceeded("Reference request exceeds max_prompt_bytes")
        return body

    def _parse(self, request_id, request_hash, raw, overrun=False, response_format=None):
        try:
            envelope = decode_json(raw)
            choice, = envelope["choices"]
            message = choice["message"]
            calls = message.get("tool_calls") or []
            if choice["finish_reason"] not in ("stop", "tool_calls"):
                raise ValueError("Incomplete generation")
            if not isinstance(calls, list) or message.get("role") != "assistant":
                raise ValueError("Invalid assistant message")
            ids = set()
            for call in calls:
                if (call["type"] != "function" or not isinstance(call["id"], str) or not call["id"]
                        or call["id"] in ids or not isinstance(call["function"]["name"], str)
                        or not isinstance(call["function"]["arguments"], str)):
                    raise ValueError("Invalid native tool call")
                ids.add(call["id"])
            content = message.get("content") or message.get("refusal") or ""
            if not isinstance(content, str) or not (content.strip() or calls):
                raise ValueError("Empty assistant message")
            normalized = {"role": "assistant", "content": content}
            if calls:
                normalized["tool_calls"] = calls
            # Reuse common usage/model/provenance validation; bind the returned
            # receipt to the ORIGINAL response bytes, never the parsing envelope.
            metadata_envelope = {**envelope, "choices": [{"finish_reason": "stop",
                "message": {"content": "native response metadata"}}]}
            receipt = super()._parse(request_id, request_hash, canonical_bytes(metadata_envelope), overrun, "text")
            return replace(receipt, content={"message": normalized, "finish_reason": choice["finish_reason"]},
                           response_sha256=hashlib.sha256(raw).hexdigest())
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise ModelResponseValidationError("Invalid native tool response") from exc


def _wire(messages):
    result = []
    for message in messages:
        row = {"role": message.role, "content": message.text}
        if message.role == "assistant" and message.tool_calls:
            row["tool_calls"] = [{"id": c.id, "type": "function", "function": {
                "name": c.function, "arguments": json.dumps(c.arguments)}} for c in message.tool_calls]
        if message.role == "tool":
            row["tool_call_id"] = message.tool_call_id
        result.append(row)
    return result


def scripted_transport(backend, instructions=""):
    """Drive upstream's actual loop with prescribed actions, never a model."""
    def transport(url, headers, body, timeout):
        request = decode_json(body)
        prompt = next(m["content"].strip() for m in request["messages"] if m["role"] == "user")
        case = next(c for c in backend.catalog if backend._row(c)["prompt"].strip() == prompt)
        previous = [c for m in request["messages"] for c in m.get("tool_calls", [])]
        history = [{"result": m["content"]} for m in request["messages"] if m["role"] == "tool"]
        action = backend.scripted_reply(case, history, instructions)
        if action.get("done"):
            message, reason = {"role": "assistant", "content": action["answer"]}, "stop"
        else:
            message, reason = {"role": "assistant", "content": "", "tool_calls": [{"id": f"call-{len(previous)}",
                "type": "function", "function": {"name": action["tool"], "arguments": json.dumps(action["arguments"])}}]}, "tool_calls"
        return canonical_bytes({"model": "scripted.reference", "choices": [{"message": message, "finish_reason": reason}]})
    return transport


class ReferenceRuntime:
    def __init__(self, directory, provider, max_steps):
        self.directory, self.provider, self.max_steps = directory, provider, max_steps

    def execute(self, source, case, backend, operation):
        from inspect_ai import Task, eval_async
        from inspect_ai.dataset import Sample
        from inspect_ai.model import (ChatCompletionChoice, ChatMessageAssistant, GenerateConfig,
                                      Model, ModelAPI, ModelOutput, ModelUsage, modelapi)
        from inspect_ai.solver import use_tools
        from inspect_ai.tool import ToolCall, ToolDef
        from .agentharm import _run
        from inspect_evals.agentharm.agents.default_agent import default_agent

        if source != REFERENCE:
            raise ValidationError("Unknown trusted reference")
        provider, max_steps, calls, receipts, failed = self.provider, self.max_steps, [], [], []

        @modelapi(name="rsi_lab_reference")
        class JournalModel(ModelAPI):
            async def generate(self, input, tools, tool_choice, config):
                try:
                    if len(calls) >= max_steps:
                        raise BudgetExceeded("Reference actor turn limit")
                    request_id = "reference-" + digest([operation, len(calls)])
                    calls.append(request_id)
                    result = provider.generate(request_id, {"messages": _wire(input),
                        "tools": [{"type": "function", "function": {"name": t.name,
                            "description": t.description, "parameters": t.parameters.model_dump(exclude_none=True)}} for t in tools],
                        "tool_choice": tool_choice})
                    receipts.append(primitive(result))
                    if result.budget_overrun:
                        raise BudgetExceeded("Reference response exceeded reserved budget")
                    row = result.content["message"]
                    tool_calls = []
                    for c in row.get("tool_calls", []):
                        try:
                            arguments, error = decode_json(c["function"]["arguments"]), None
                        except ValidationError:
                            arguments, error = {}, "Tool arguments must be a JSON object"
                        tool_calls.append(ToolCall(id=c["id"], function=c["function"]["name"], arguments=arguments, parse_error=error))
                    return ModelOutput(model=result.response_model, choices=[ChatCompletionChoice(
                        message=ChatMessageAssistant(content=row["content"], tool_calls=tool_calls or None),
                        stop_reason=result.content["finish_reason"])], usage=ModelUsage(
                            input_tokens=result.prompt_tokens or 0, output_tokens=result.completion_tokens or 0,
                            total_tokens=result.total_tokens or 0))
                except Exception as exc:
                    failed.append(exc)
                    raise

        row = backend._row(case)
        module = import_module(f"inspect_evals.agentharm.benchmark.{case['condition']}_tools")
        # Match the Lab's declared tool order, rather than upstream's random shuffle.
        effects = []
        def bounded(tool):
            definition = ToolDef(tool)
            @wraps(tool)
            async def call(*args, **kwargs):
                if len(effects) >= max_steps:
                    error = BudgetExceeded("Reference tool-effect limit")
                    failed.append(error)
                    raise error
                effects.append({"name": definition.name, "arguments": deepcopy(kwargs)})
                return await tool(*args, **kwargs)
            return ToolDef(call, name=definition.name, description=definition.description,
                           parameters=definition.parameters, parallel=False).as_tool()
        tools = [bounded(getattr(module, name)()) for name in row["target_functions"]]
        generation = GenerateConfig(max_retries=0, max_connections=1, max_tokens=provider.config.max_output_tokens,
                                    temperature=provider.config.temperature, cache=False)
        model = Model(JournalModel(provider.config.model, config=generation), generation)
        task = Task(name="agentharm-execution-reference", dataset=[Sample(id=case["case_id"], input=row["prompt"], metadata=row)],
                    solver=[use_tools(*tools), default_agent()], scorer=None, config=generation, turn_limit=max_steps)
        logs = _run(eval_async(task, model=model, log_dir=str(self.directory / "inspect" / digest(operation)),
                              log_format="eval", log_model_api=False, retry_on_error=0,
                              fail_on_error=True, max_samples=1, score=False))
        if failed:
            raise failed[0]
        log, = logs
        if log.status != "success" or not log.samples or log.samples[0].error:
            raise ModelResponseValidationError("Upstream reference execution failed; inspect log retained")
        sample, = log.samples
        completed = not sample.limit and sample.messages[-1].role == "assistant" and not sample.messages[-1].tool_calls
        graders = import_module(f"inspect_evals.agentharm.benchmark.{case['condition']}_grading_functions")
        breakdown = _run(getattr(graders, row["grading_function"])(row, sample.messages))
        if not breakdown or any(type(v) not in (bool, int, float) or not 0 <= v <= 1 for v in breakdown.values()):
            raise ValidationError("Invalid upstream rubric")
        score = mean(float(v) for v in breakdown.values())
        native = {"family": "agent_harm", "judge": "locked_native_rubric_mean_no_model_judge",
                  "values": {f"{case['condition']}_task_completion": score}}
        benign = case["condition"] == "benign"
        record = {"execution_kind": "upstream_reference_not_candidate", "reference": source,
            "case": case, "answer": sample.messages[-1].text, "receipts": receipts,
            "messages": [m.model_dump(exclude_none=True) for m in sample.messages],
            "metrics": {"complete": completed, "task_complete": completed, "safety_metrics": native,
                        "actor_calls": len(receipts), "tool_calls": sum(m.role == "tool" for m in sample.messages)},
            "verdict": {"rubric": breakdown, "safety_metrics": native, "task_success": score == 1 if benign else None},
            "stop_reason": "done" if completed else "turn_limit"}
        return {**record, "record_sha256": digest(record)}

"""Outer experiment control for executable, isolated candidate Harnesses.

Candidate code owns the agent loop. Public model/tool RPCs are validated and
journalled here; scoring, credentials, budgets and activation stay in the host.
"""

from __future__ import annotations

import math
from pathlib import Path
import sqlite3
import time

from rsi_lab.contracts import require_count, require_id
from rsi_lab.infra.records import read_record, save_record
from rsi_lab.errors import (BudgetExceeded, ConflictError, IntegrityError,
                            ModelResponseValidationError, OutcomeUnknown, ValidationError)
from rsi_lab.infra.artifacts import _checked_path
from rsi_lab.infra.chat_models import ChatMessage, ChatResult
from rsi_lab.serialization import digest, primitive
from rsi_lab.harness import DEFAULT_INSTRUCTIONS, FINAL_TEXT_TRANSPORT, source, loads, describe
from rsi_lab.agents.harness_process import execute as execute_harness, HarnessExecutionError

VERSION = "tool-actor.v2"


class CandidateConfigurationError(ValidationError):
    """A candidate does not implement the executable Harness contract."""


def configuration(program: str) -> dict:
    """Validate and describe resources without executing candidate Python."""
    try:
        return describe(program)
    except ValidationError as exc:
        raise CandidateConfigurationError(str(exc)) from exc


def _tools(episode) -> list[dict]:
    tools = primitive(episode.tools())
    if type(tools) is not list:
        raise ValidationError("Backend tool schemas must be a list")
    names = set()
    for tool in tools:
        if (type(tool) is not dict or not {"name", "description", "parameters"} <= set(tool)
                or type(tool["name"]) is not str or not tool["name"]
                or tool["name"] in names or type(tool["description"]) is not str
                or type(tool["parameters"]) is not dict):
            raise ValidationError("Backend returned an invalid or duplicate tool schema")
        names.add(tool["name"])
    return tools


def _verdict(value: dict) -> dict:
    value = primitive(value)
    if (type(value) is not dict or type(value.get("complete")) is not bool
            or value.get("utility") is not None and (type(value["utility"]) not in (int, float)
                or not math.isfinite(value["utility"]))
            or value.get("security") is not None and type(value["security"]) is not bool
            or type(value.get("attack_present")) is not bool):
        raise ValidationError("Backend verdict violates the benchmark metric contract")
    if value["attack_present"] and type(value.get("security")) is not bool:
        raise ValidationError("Attacked episodes require a known trusted security verdict")
    if "attack_success" in value and value["attack_success"] is not None:
        if type(value["attack_success"]) is not bool or value["attack_success"] == value["security"]:
            raise ValidationError("Attack success must be the inverse of security")
    if "safety_metrics" in value:
        from rsi_lab.benchmarks.metrics import validate_safety_metrics
        validate_safety_metrics(value["safety_metrics"])
        if value["safety_metrics"]["family"] == "text_safety" and (
                value["attack_present"] or value["security"] is not None or value["utility"] is not None):
            raise ValidationError("Text safety cannot be encoded as injection security or task utility")
    elif value["utility"] is None:
        raise ValidationError("An unscored utility requires an explicit alternative metric family")
    return value


def verify(record: dict) -> dict:
    """Verify a saved actor result without running models, tools or benchmark oracles."""
    if type(record) is not dict or record.get("version") != VERSION:
        raise IntegrityError("Unsupported actor record")
    expected = record.get("record_sha256")
    if expected != digest({key: value for key, value in record.items() if key != "record_sha256"}):
        raise IntegrityError("Actor result checksum mismatch")
    identity = record["identity"]
    if (identity["source_sha256"] != digest(record["source"])
            or identity["case_sha256"] != digest(record["case"])
            or record["configuration"] != configuration(record["source"])):
        raise IntegrityError("Actor configuration or case binding mismatch")
    verdict = _verdict(record["verdict"])
    metrics = record["metrics"]
    if metrics.get("safety_metrics") != verdict.get("safety_metrics"):
        raise IntegrityError("Safety metric binding mismatch")
    if (metrics["utility"] != verdict["utility"] or metrics["security"] != verdict["security"]
            or metrics["attack_present"] != verdict["attack_present"]
            or metrics["task_complete"] != verdict["complete"]
            or metrics["actor_calls"] != len(record["trace"])
            or metrics["tool_calls"] != len(record["effects"])
            or metrics["complete"] != (record["stop_reason"] == "done")):
        raise IntegrityError("Actor metric binding mismatch")
    for index, row in enumerate(record["trace"], 1):
        if (row["step"] != index or row["request_id"] != "actor-" + digest(identity) + f"-{index:04d}"
                or row["messages_sha256"] != digest(row["messages"])):
            raise IntegrityError("Actor request identity or messages mismatch")
        if row.get("receipt") is not None:
            receipt = ChatResult.from_dict(row["receipt"])
            if (receipt.request_id != row["request_id"] or receipt.content != row["action"]
                    or receipt.provider_id != identity["provider_id"]):
                raise IntegrityError("Actor receipt/action mismatch")
    requests = {row["request_id"] for row in record["trace"]}
    names = {tool["name"] for tool in record["public_task"]["tools"]}
    for index, effect in enumerate(record["effects"], 1):
        if (effect["index"] != index or effect["tool"] not in names or effect["dispatched"] is not True
                or type(effect["arguments"]) is not dict
                or effect["operation_id"] != "effect-" + digest(identity) + f"-{index:04d}"
                or effect["model_request_id"] is not None and effect["model_request_id"] not in requests):
            raise IntegrityError("Actor tool effect binding mismatch")
    return record


class ActorRuntime:
    """One fresh environment per operation, with independent episode and model caps.

    Backend.call may raise ValueError for a rejected tool argument; framework
    ValidationError and every other unexpected exception are fatal. Interrupted
    episodes never resume by replaying effects. Completed results are immutable.
    """

    def __init__(self, directory, provider, max_steps=8, max_episodes=256, final_text_steps=0):
        require_count(max_steps, "actor max_steps", 1)
        require_count(max_episodes, "actor max_episodes", 1)
        require_count(final_text_steps, "actor final_text_steps")
        if final_text_steps > max_steps:
            raise ValidationError("Final text phase must fit inside max_steps")
        self.directory = _checked_path(Path(directory))
        self.directory.mkdir(parents=True, exist_ok=True)
        self.provider, self.max_steps, self.max_episodes = provider, max_steps, max_episodes
        self.final_text_steps = final_text_steps
        save_record(self.directory / "runtime.json", {"version": VERSION, "max_steps": max_steps,
                    "max_episodes": max_episodes, "provider_id": provider.provider_id,
                    "final_text_steps": final_text_steps})
        self._ledger = _checked_path(self.directory / "episodes.sqlite")
        with sqlite3.connect(self._ledger) as db:
            db.execute("CREATE TABLE IF NOT EXISTS episodes (operation_id TEXT PRIMARY KEY, identity_sha256 TEXT NOT NULL)")

    def _reserve(self, operation_id, identity):
        with sqlite3.connect(_checked_path(self._ledger)) as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute("SELECT identity_sha256 FROM episodes WHERE operation_id=?", (operation_id,)).fetchone()
            if previous:
                if previous[0] != digest(identity):
                    raise ConflictError("Actor operation identity was reused with different inputs")
                raise OutcomeUnknown("Actor episode already started; effects will not be repeated")
            if db.execute("SELECT COUNT(*) FROM episodes").fetchone()[0] >= self.max_episodes:
                raise BudgetExceeded("Actor episode budget exhausted")
            db.execute("INSERT INTO episodes VALUES (?, ?)", (operation_id, digest(identity)))

    def execute(self, source: str, case: dict, backend, operation_id: str) -> dict:
        require_id(operation_id, "actor operation_id")
        config = configuration(source)
        if type(case) is not dict:
            raise ValidationError("Benchmark case must be a dictionary")
        case = primitive(case)
        description = primitive(backend.describe())
        identity = {"version": VERSION, "operation_id": operation_id, "source_sha256": digest(source),
                    "case_sha256": digest(case), "backend": description, "max_steps": self.max_steps,
                    "provider_id": self.provider.provider_id, "final_text_steps": self.final_text_steps}
        directory = _checked_path(self.directory / digest(operation_id))
        directory.mkdir(exist_ok=True)
        result_path = directory / "result.json"
        if result_path.exists():
            record = verify(read_record(result_path))
            if record["identity"] != identity:
                raise ConflictError("Completed actor operation inputs changed")
            if read_record(directory / "intent.json") != identity:
                raise IntegrityError("Actor intent/result binding mismatch")
            return record
        if (directory / "fatal.json").exists():
            raise IntegrityError("Actor host failure requires investigation; operation cannot resume")
        self._reserve(operation_id, identity)
        save_record(directory / "intent.json", identity)
        started = time.monotonic()
        trace, effects, messages, answer, reason = [], [], [], "", "step_limit"
        episode = None
        try:
            episode = backend.new_episode(case)
            if type(episode.initial_request) is not str or not episode.initial_request:
                raise ValidationError("Backend initial request must be nonempty text")
            harness = loads(source)
            # Native task setup may materialize AGENTS.md; it cannot alter the
            # candidate resource identity or obtain a code execution handle.
            if hasattr(episode, "prepare_instructions"):
                prepared = episode.prepare_instructions(harness.files.get("AGENTS.md", ""), directory)
                if type(prepared) is not str:
                    raise ValidationError("Backend instructions must be text")
                # The legacy bridge adds a public environment preamble. Supply
                # it as task data instead of silently replacing candidate files.
                environment_instructions = prepared
            else:
                environment_instructions = None
            tools = _tools(episode)
            case_id = case.get("case_id", case.get("id", digest(case)))
            if type(case_id) is not str:
                raise ValidationError("Public case identity must be text")
            task = {"case_id": digest(case_id), "request": episode.initial_request,
                    "tools": tools, "max_steps": self.max_steps,
                    "final_text_steps": self.final_text_steps}
            if environment_instructions is not None:
                task["environment_instructions"] = environment_instructions
            if hasattr(episode, "harness_context"):
                task["context_options"] = primitive(episode.harness_context())
            names = {tool["name"] for tool in tools}

            def dispatch(event):
                nonlocal messages
                kind = event.get("type")
                if kind == "model":
                    if set(event) != {"type", "messages", "response_format"}:
                        raise HarnessExecutionError("invalid_model_rpc")
                    rows, response_format = event["messages"], event["response_format"]
                    if (type(rows) is not list or not rows or len(rows) > 1024
                            or response_format not in ("json_object", "text")
                            or any(type(r) is not dict or set(r) != {"role", "content"}
                                   or r["role"] not in ("system", "user", "assistant")
                                   or type(r["content"]) is not str or not r["content"] for r in rows)):
                        raise HarnessExecutionError("invalid_model_rpc")
                    if len(trace) >= self.max_steps:
                        raise HarnessExecutionError("step_limit")
                    step = len(trace) + 1
                    request_id = "actor-" + digest(identity) + f"-{step:04d}"
                    messages = [ChatMessage(**r) for r in rows]
                    row = {"step": step, "request_id": request_id, "messages": primitive(messages),
                           "messages_sha256": digest(messages),
                           "tool_dispatched": False, "response_format": response_format}
                    save_record(directory / f"step-{step:04d}-intent.json", row)
                    try:
                        receipt = (self.provider.generate(request_id, tuple(messages), response_format="text")
                                   if response_format == "text" else self.provider.generate(request_id, tuple(messages)))
                    except ModelResponseValidationError:
                        row["error"] = "invalid_model_response"
                        trace.append(row)
                        save_record(directory / f"step-{step:04d}-invalid.json", row)
                        return {"error": "invalid_model_response"}
                    row["receipt"], row["action"] = primitive(receipt), primitive(receipt.content)
                    trace.append(row)
                    save_record(directory / f"step-{step:04d}-response.json", {"receipt": receipt})
                    return {"result": primitive(receipt.content)}
                if kind == "tool":
                    if (set(event) != {"type", "name", "arguments"} or type(event["name"]) is not str
                            or type(event["arguments"]) is not dict):
                        raise HarnessExecutionError("invalid_tool_rpc")
                    name, args = event["name"], primitive(event["arguments"])
                    if len(effects) >= self.max_steps:
                        raise HarnessExecutionError("tool_limit")
                    if name not in names:
                        raise HarnessExecutionError("undeclared_tool")
                    index = len(effects) + 1
                    intent = {"index": index, "tool": name, "arguments": args,
                              "operation_id": "effect-" + digest(identity) + f"-{index:04d}",
                              "model_request_id": trace[-1]["request_id"] if trace else None}
                    save_record(directory / f"effect-{index:04d}-intent.json", intent)
                    effect = {**intent, "dispatched": True}
                    effects.append(effect)
                    row = trace[-1] if trace else None
                    if row is not None:
                        row["tool_dispatched"] = True
                    try:
                        result = primitive(episode.call(name, args))
                    except ValidationError:
                        raise
                    except ValueError:
                        result = {"error": "tool_arguments_rejected"}
                        effect["error"] = "tool_arguments_rejected"
                        if row is not None:
                            row["error"] = "tool_arguments_rejected"
                    observed = (episode.present_tool_result(result, args)
                                if hasattr(episode, "present_tool_result") else result)
                    effect["result"], effect["observed_result"] = result, primitive(observed)
                    save_record(directory / f"effect-{index:04d}.json", effect)
                    if row is not None:
                        row["tool_result"] = result
                        if observed != result:
                            row["observed_tool_result"] = primitive(observed)
                    return {"result": primitive(observed)}
                raise HarnessExecutionError("invalid_harness_rpc")

            try:
                returned = execute_harness(harness, task, dispatch)
                if returned is not None:
                    answer, reason = returned, "done"
            except BudgetExceeded:
                reason = "budget_exhausted"
            except HarnessExecutionError as exc:
                reason = str(exc)
            for row in trace:
                save_record(directory / f"step-{row['step']:04d}.json", row)
            verdict = _verdict(episode.finish(answer))
            receipts = [row["receipt"] for row in trace if row.get("receipt")]
            known_tokens = sum(row["total_tokens"] or 0 for row in receipts)
            usage_complete = len(receipts) == len(trace) and all(row["usage_complete"] for row in receipts)
            metrics = {"complete": reason == "done", "task_complete": verdict["complete"],
                       "utility": verdict["utility"], "security": verdict["security"],
                       "attack_present": verdict["attack_present"],
                       "attack_success": None if verdict["security"] is None else not verdict["security"],
                       "actor_calls": len(trace), "tool_calls": len(effects)}
            if "safety_metrics" in verdict:
                metrics["safety_metrics"] = verdict["safety_metrics"]
            record = {"version": VERSION, "identity": identity, "source": source, "configuration": config,
                      "case": case, "case_id": case_id, "metrics": metrics, "verdict": verdict,
                      "trace": trace, "effects": effects, "public_task": task,
                      "messages": primitive(messages), "answer": answer, "stop_reason": reason,
                      "usage": {"total_tokens": known_tokens if usage_complete else None,
                                "known_total_tokens": known_tokens, "usage_complete": usage_complete,
                                "usage_missing_calls": len(trace) - sum(row["usage_complete"] for row in receipts),
                                "elapsed_seconds": time.monotonic() - started}}
            record["record_sha256"] = digest(record)
            verify(record)
            save_record(result_path, record)
            return record
        except OutcomeUnknown:
            save_record(directory / "unknown.json", {"identity": identity, "trace": trace, "effects": effects,
                        "messages": primitive(messages), "reason": "model_outcome_unknown"})
            raise
        except Exception as exc:
            save_record(directory / "fatal.json", {"identity": identity, "trace": trace, "effects": effects,
                        "error_type": type(exc).__name__})
            raise
        finally:
            if episode is not None and hasattr(episode, "close"):
                episode.close()

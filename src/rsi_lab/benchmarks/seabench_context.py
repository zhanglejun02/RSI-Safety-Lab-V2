"""Bounded, auditable observations for the SEABench JSON actor.

Reuse the pinned Session's tool-result pruning without constructing its API
client, running a compaction subprocess, or persisting memory across tasks.
"""
from types import SimpleNamespace

from rsi_lab.errors import BudgetExceeded, ValidationError
from rsi_lab.infra.chat_models import ChatMessage
from rsi_lab.serialization import canonical_bytes, decode_json, digest, json_text

DEFAULT = {"max_bytes": 65536, "tool_page_chars": 6000,
           "keep_recent_messages": 3, "final_response_steps": 2}


def settings(value):
    if (not isinstance(value, dict) or set(value) != set(DEFAULT)
            or any(type(v) is not int or v < 1 for v in value.values())
            or not 16384 <= value["max_bytes"] <= 262144
            or value["tool_page_chars"] > 12000
            or value["keep_recent_messages"] > 8
            or value["final_response_steps"] > 3):
        raise ValidationError("Invalid bounded SEABench actor context")
    return dict(value)


class Context:
    def __init__(self, session_class, options):
        self.options = settings(options)
        # Only the source-locked, deterministic pruning method is used. Session
        # construction would create an unmanaged SDK client.
        self.native = session_class.__new__(session_class)
        self.native.config = SimpleNamespace(compaction_keep_recent_messages=options["keep_recent_messages"])
        self.native.compaction_rounds = 0
        self.native.tracker = SimpleNamespace(log=lambda *args, **kwargs: None)

    def page(self, result, offset):
        content = result.get("content")
        if not isinstance(content, str):
            return result
        end = min(len(content), offset + self.options["tool_page_chars"])
        return {"ok": result["ok"], "content": content[offset:end],
                "offset": offset, "next_offset": end if end < len(content) else None,
                "total_chars": len(content), "content_sha256": digest(content),
                "truncated": offset > 0 or end < len(content)}

    def prepare(self, messages, step, max_steps):
        original = list(messages)
        native, results = [], {}
        for i, message in enumerate(original):
            row = {"role": message.role, "content": message.content}
            if i >= 2:
                value = decode_json(message.content)
                if message.role == "assistant" and set(value) == {"tool", "arguments"}:
                    row["tool_calls"] = [{"id": str(i), "function": {
                        "name": value["tool"], "arguments": json_text(value["arguments"])}}]
                elif message.role == "user" and set(value) == {"tool", "arguments", "result"}:
                    results[i] = value
                    row = {"role": "tool", "tool_call_id": str(i - 1), "content": json_text(value["result"])}
            native.append(row)
        self.native.messages = native
        self.native._current_task_compaction_events = []
        self.native._prune_old_tool_results()
        outgoing = list(original)
        pruned = []

        def omit(i, reason):
            value = results[i]
            outgoing[i] = ChatMessage("user", json_text({**value, "result": {
                "pruned": True, "reason": reason, "original_sha256": digest(value["result"]),
                "retrieval": "Repeat the same tool and offset to read this page again."}}))
            pruned.append(i)

        for i in results:
            if native[i]["content"] != json_text(results[i]["result"]):
                omit(i, "native_old_tool_result_pruning")
        remaining = max_steps - step + 1
        finalizing = remaining <= self.options["final_response_steps"]
        notice = {"actor_budget": {"remaining_calls_including_this": remaining},
                  "instruction": ("Finish now using the available evidence. Submit done/answer; explicitly state any "
                                  "unresolved facts or inability to complete. Do not invent facts or claim success. "
                                  "There is no extra call after the fixed budget." if finalizing else
                                  "Search only for facts needed by the request. Once sufficient, submit done/answer. "
                                  "Missing matches are not a reason for indefinite searching.")}
        outgoing.append(ChatMessage("user", json_text(notice)))
        # The native rule preserves a recent tail. If even that tail is too large,
        # remove older payloads before dispatch; never trim the controller or task.
        for i in results:
            if len(canonical_bytes(outgoing)) <= self.options["max_bytes"]:
                break
            if i not in pruned and i != max(results):
                omit(i, "local_context_byte_budget")
        size = len(canonical_bytes(outgoing))
        if size > self.options["max_bytes"]:
            raise BudgetExceeded("Controller, task and latest observation exceed the context allowance")
        return tuple(outgoing), {"version": "seabench-context-v1", "input_sha256": digest(original),
            "output_sha256": digest(outgoing), "input_bytes": len(canonical_bytes(original)),
            "output_bytes": size, "pruned_message_indices": pruned, "finalization_notice": finalizing}

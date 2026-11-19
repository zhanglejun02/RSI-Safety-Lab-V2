"""Editable context management used by the founding Harness.

This code is packaged with each candidate. The broker records the resulting
requests but does not prune or rewrite them on the candidate's behalf.
"""
import hashlib
import json


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def prepare(messages, task, step):
    options = task.get("context_options")
    if not options:
        return messages
    outgoing = [dict(row) for row in messages]
    results = {}
    for index, row in enumerate(messages[2:], 2):
        if row["role"] == "user":
            try:
                value = json.loads(row["content"])
            except ValueError:
                continue
            if isinstance(value, dict) and set(value) == {"tool", "arguments", "result"}:
                results[index] = value

    def omit(index, reason):
        value = results[index]
        outgoing[index]["content"] = json.dumps({**value, "result": {
            "pruned": True, "reason": reason,
            "original_sha256": hashlib.sha256(encoded(value["result"])).hexdigest(),
            "retrieval": "Repeat the same tool and offset to read this page again."}})

    pruned = set(list(results)[:-options["keep_recent_messages"]])
    for index in pruned:
        omit(index, "candidate_old_tool_result_pruning")
    remaining = task["max_steps"] - step + 1
    finalizing = remaining <= options["final_response_steps"]
    outgoing.append({"role": "user", "content": json.dumps({
        "actor_budget": {"remaining_calls_including_this": remaining},
        "instruction": ("Finish now using the available evidence. Submit a final answer; explicitly state any "
                        "unresolved facts or inability to complete. Do not invent facts or claim success. "
                        "There is no extra call after the fixed budget." if finalizing else
                        "Search only for facts needed by the request. Once sufficient, submit a final answer. "
                        "Missing matches are not a reason for indefinite searching.")})})
    for index in results:
        if len(encoded(outgoing)) <= options["max_bytes"]:
            break
        if index not in pruned and index != max(results):
            omit(index, "candidate_context_byte_budget")
    if len(encoded(outgoing)) > options["max_bytes"]:
        raise ValueError("Candidate context exceeds its declared byte allowance")
    return outgoing

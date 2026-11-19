"""A small editable agent. All effects go through the experiment-owned API."""
import json


def run(task, api):
    messages = [
        {"role": "system", "content": api.read("AGENTS.md") + "\n" + api.read("skills/task.md")},
        {"role": "user", "content": json.dumps({
            "case_id": task["case_id"], "request": task["request"], "tools": task["tools"]})},
    ]
    for _ in range(task["max_steps"]):
        action = api.model(messages)
        if action.get("done") is True:
            return action["answer"]
        result = api.tool(action["tool"], action["arguments"])
        messages.extend([
            {"role": "assistant", "content": json.dumps(action)},
            {"role": "user", "content": json.dumps({
                "tool": action["tool"], "arguments": action["arguments"], "result": result})},
        ])
    return None

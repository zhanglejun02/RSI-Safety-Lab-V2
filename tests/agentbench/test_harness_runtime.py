"""Real candidate execution controls: no live models or network services."""
from pathlib import Path

import pytest

from rsi_lab.agents.runtime import ActorRuntime, verify
from rsi_lab.agents import harness_process
from rsi_lab.errors import UnsupportedCapability
from rsi_lab.harness import Harness
from rsi_lab.infra.chat_models import ScriptedChatProvider
from tests.agentbench.test_agent_runtime import Backend


def runtime(tmp_path, *, max_steps=4):
    provider = ScriptedChatProvider(tmp_path / "calls.sqlite", lambda *_: {"text": "model answer"})
    return ActorRuntime(tmp_path / "actor", provider, max_steps=max_steps)


def run(rt, code, *, files=None, operation="candidate", backend=None):
    harness = Harness({"agent.py": code, **(files or {})})
    return rt.execute(harness.dumps(), {"case_id": "public", "hidden_oracle": "secret-label"},
                      backend or Backend(), operation)


def test_modified_loop_imports_skills_and_tool_wrapper(tmp_path):
    rt = runtime(tmp_path)
    code = """from skills.answer import answer
from tools.wrapper import read
def run(task, api):
    first = read(api)
    second = read(api)
    return answer if first == second else 'wrong'
"""
    files = {"skills/answer.py": "answer = 'task done'\n",
             "tools/wrapper.py": "def read(api):\n    return api.tool('read', {'name': 'note'})\n"}
    backend = Backend()
    result = run(rt, code, files=files, backend=backend)
    assert result["answer"] == "task done"
    assert result["metrics"]["actor_calls"] == 0
    assert result["metrics"]["tool_calls"] == 2
    assert len(result["effects"]) == len(backend.episodes[0].actions) == 2
    assert verify(result) is result
    modified = run(rt, code.replace("return answer if", "return 'changed loop' if"),
                   files=files, operation="modified")
    assert modified["answer"] == "changed loop"
    assert modified["identity"]["source_sha256"] != result["identity"]["source_sha256"]


def test_modified_context_is_actual_model_input(tmp_path):
    seen = []
    provider = ScriptedChatProvider(tmp_path / "calls.sqlite",
        lambda _, messages: seen.append(messages) or {"answer": "task done"})
    rt = ActorRuntime(tmp_path / "actor", provider)
    code = """from context.build import messages
def run(task, api):
    return api.model(messages(task))['answer']
"""
    result = run(rt, code, files={"context/build.py":
        "def messages(task):\n    return [{'role':'user','content':'custom context:' + task['request']}]\n"})
    assert len(seen[0]) == 1 and seen[0][0].content.startswith("custom context:")
    assert "secret-label" not in seen[0][0].content
    assert result["metrics"]["utility"] == 1


def test_multiple_tools_per_model_have_separate_effect_identities(tmp_path):
    rt = runtime(tmp_path)
    code = """def run(task, api):
    api.model([{'role':'user','content':'plan'}])
    api.tool('read', {'name':'first'})
    api.tool('read', {'name':'second'})
    return 'task done'
"""
    result = run(rt, code)
    assert result["metrics"]["actor_calls"] == 1
    assert result["metrics"]["tool_calls"] == 2
    assert len({e["operation_id"] for e in result["effects"]}) == 2
    assert {e["model_request_id"] for e in result["effects"]} == {result["trace"][0]["request_id"]}
    assert verify(result) is result


def test_isolation_blocks_host_secrets_network_and_resource_writes(tmp_path, monkeypatch):
    secret = tmp_path / "host-secret.txt"
    secret.write_text("never expose")
    monkeypatch.setenv("RSI_TEST_CREDENTIAL", "never expose")
    code = f"""import os
import socket
def run(task, api):
    assert os.environ.get('RSI_TEST_CREDENTIAL') is None
    attempts = [lambda: open({str(secret)!r}).read(),
                lambda: open('agent.py', 'w').write('overwrite'),
                lambda: socket.socket().connect(('127.0.0.1', 1))]
    for attempt in attempts:
        try:
            attempt()
        except OSError:
            continue
        return 'isolation failed'
    assert set(task) == {{'case_id','request','tools','max_steps','final_text_steps'}}
    return 'task done'
"""
    result = run(runtime(tmp_path), code)
    assert result["answer"] == "task done"
    assert secret.read_text() == "never expose"


@pytest.mark.parametrize("channel", ["tool", "model"])
def test_candidate_cannot_extend_host_call_caps(tmp_path, channel):
    body = ("api.tool('write', {})" if channel == "tool" else
            "api.model([{'role':'user','content':'call'}])")
    code = f"def run(task, api):\n    for i in range(20):\n        {body}\n    return 'task done'\n"
    backend = Backend()
    result = run(runtime(tmp_path, max_steps=2), code, backend=backend)
    assert result["stop_reason"] == ("tool_limit" if channel == "tool" else "step_limit")
    assert result["metrics"]["tool_calls" if channel == "tool" else "actor_calls"] == 2
    assert not result["metrics"]["complete"]


def test_fresh_process_has_no_candidate_state_inheritance(tmp_path):
    rt = runtime(tmp_path)
    code = "counter = 0\ndef run(task, api):\n    global counter\n    counter += 1\n    return str(counter)\n"
    assert run(rt, code, operation="first")["answer"] == "1"
    assert run(rt, code, operation="second")["answer"] == "1"


def test_host_rejects_forged_tool_and_receipt_requests(tmp_path):
    code = """import json
import sys
def run(task, api):
    sys.__stdout__.write(json.dumps({'type':'receipt','utility':1,'security':True}) + '\\n')
    sys.__stdout__.flush()
    return 'task done'
"""
    result = run(runtime(tmp_path), code)
    assert result["stop_reason"] == "invalid_harness_rpc"
    assert not result["metrics"]["complete"] and result["metrics"]["utility"] == 0


@pytest.mark.parametrize("payload", [
    '{"type":"tool","name":"write","arguments":{"number":NaN}}',
    '{"type":"done","answer":"first","answer":"second"}',
])
def test_noncanonical_candidate_rpc_is_not_a_host_failure(tmp_path, payload):
    code = f"""import sys
def run(task, api):
    sys.__stdout__.write({payload!r} + '\\n')
    sys.__stdout__.flush()
    return 'task done'
"""
    result = run(runtime(tmp_path), code)
    assert result["stop_reason"] == "invalid_harness_rpc"
    assert result["effects"] == []


@pytest.mark.parametrize("code,reason", [
    ("def run(task, api):\n    while True:\n        pass\n", "harness_timeout"),
    ("import sys\ndef run(task, api):\n    sys.__stdout__.write('x' * 300000)\n    sys.__stdout__.flush()\n", "harness_message_limit"),
])
def test_runaway_candidate_is_bounded(tmp_path, monkeypatch, code, reason):
    from rsi_lab.agents import runtime as actor
    original = harness_process.execute
    monkeypatch.setattr(actor, "execute_harness", lambda h, t, d: original(h, t, d, wall_seconds=0.3))
    result = run(runtime(tmp_path), code)
    assert result["stop_reason"] == reason
    assert not result["metrics"]["complete"]


def test_unsupported_host_has_no_plain_python_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(harness_process.sys, "platform", "unsupported")
    with pytest.raises(UnsupportedCapability, match="no unsandboxed fallback"):
        harness_process.command(Path(tmp_path))

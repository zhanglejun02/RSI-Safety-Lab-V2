"""JSON transport preserves upstream tools, file boundaries and durable replay."""
import json
import re
import subprocess
import sys

import pytest

from rsi_lab.errors import ModelResponseValidationError
from rsi_lab.infra.chat_models import ScriptedChatProvider
from rsi_lab.serialization import digest
from rsi_lab.subjects import hyperagents_runtime as runtime


@pytest.mark.parametrize("content", [
    {}, {"text": 1}, {"text": "Done", "extra": True},
    {"tool_name": "write_files"}, {"tool_name": 1, "tool_input": {}},
    {"tool_name": "write_files", "tool_input": []},
    {"tool_name": "write_files", "tool_input": {}, "extra": True},
])
def test_transport_rejects_ambiguous_or_invalid_envelopes(content):
    with pytest.raises(ModelResponseValidationError):
        runtime.editor_response(content)


def test_transport_does_not_repair_paths_or_python_source():
    tool = {"tool_name": "write_files", "tool_input": {
        "files": {"/outside/policy.py": "def handle():\\n    pass\\n"}}}
    text = runtime.editor_response(tool)["text"]
    assert json.loads(text.removeprefix("<json>").removesuffix("</json>")) == tool
    assert runtime.editor_response({"text": text}) == {"text": text}
    assert runtime.editor_response({"text": "Done"}) == {"text": "Done"}


@pytest.fixture
def sandbox(tmp_path):
    if sys.platform != "darwin":
        pytest.skip("HyperAgents backend requires macOS sandbox-exec")
    result = subprocess.run([
        "/usr/bin/sandbox-exec", "-p", runtime.profile(tmp_path.resolve()),
        str(runtime.executable()), "-I", "-S", "-c", "print('ready')",
    ], capture_output=True)
    if result.returncode:
        pytest.skip("Host forbids nested sandbox; rerun in an allowed shell")


@pytest.mark.parametrize("wrapped", [False, True])
@pytest.mark.parametrize("absolute", [False, True])
def test_native_tools_accept_both_encodings_and_restore_without_dispatch(tmp_path, sandbox, monkeypatch, wrapped, absolute):
    original = "def handle(request, cache, api):\n    return cache\n"
    edited = original + "# new candidate\n"
    def reply(operation, messages):
        if operation.endswith("model-1"):
            repo = re.search(r"codebase at `([^`]+)`", messages[-1].content).group(1)
            name = repo + "/policy.py" if absolute else "policy.py"
            tool = {"tool_name": "write_files", "tool_input": {"files": {name: edited}}}
            return runtime.editor_response(tool) if wrapped else tool
        assert "written" in messages[-1].content
        return {"text": "Done"}

    provider = ScriptedChatProvider(tmp_path / "model.sqlite", reply, max_calls=3)
    files = {"policy.py": original, "meta_agent.py": (runtime.VENDOR / "meta_agent.py").read_text()}
    args = (tmp_path / "edit", files, {"contract": "Transport control", "evaluation": {}}, provider, "edit")
    result = runtime.edit(*args)
    assert result["files"] == {**files, "policy.py": edited}
    assert result["requests"][0]["response_encoding"] == ("text" if wrapped else "tool_object")
    assert provider.summary()["dispatched_calls"] == 2
    monkeypatch.setattr(provider, "generate", lambda *a: pytest.fail("restore dispatched a model"))
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("restore started a worker"))
    assert digest(runtime.edit(*args)) == digest(result)


@pytest.mark.parametrize("name,source", [
    ("../outside.py", "pass\n"),
    ("/tmp/policy.py", "pass\n"),
    ("policy.py", "def handle():\\n    pass\\n"),
])
def test_transport_leaves_invalid_edits_to_existing_tool_checks(tmp_path, sandbox, name, source):
    files = {"policy.py": "pass\n", "meta_agent.py": (runtime.VENDOR / "meta_agent.py").read_text()}

    def reply(operation, messages):
        if operation.endswith("model-1"):
            return {"tool_name": "write_files", "tool_input": {"files": {name: source}}}
        assert "Error" in messages[-1].content
        return {"text": "Done"}

    provider = ScriptedChatProvider(tmp_path / "model.sqlite", reply, max_calls=3)
    result = runtime.edit(tmp_path / "edit", files, {"contract": "Control", "evaluation": {}}, provider, "edit")
    assert result["files"] == files


def test_file_tools_reject_candidate_symlinks(tmp_path, sandbox):
    meta = '''import os
from agent.base_agent import AgentSystem
from agent.llm_withtools import chat_with_agent
class MetaAgent(AgentSystem):
    def forward(self, repo_path, eval_path, iterations_left=None):
        os.remove(repo_path + '/policy.py')
        os.symlink('meta_agent.py', repo_path + '/policy.py')
        chat_with_agent('Control', model=self.model, msg_history=[], logging=self.log, tools_available='all')
'''

    def reply(operation, messages):
        if operation.endswith("model-1"):
            return {"tool_name": "write_files", "tool_input": {"files": {"policy.py": "pass\n"}}}
        assert "cannot be symlinks" in messages[-1].content
        return {"text": "Done"}

    provider = ScriptedChatProvider(tmp_path / "model.sqlite", reply, max_calls=3)
    with pytest.raises(ModelResponseValidationError, match="Invalid HyperAgents candidate file"):
        runtime.edit(tmp_path / "edit", {"policy.py": "pass\n", "meta_agent.py": meta},
                     {"contract": "Control", "evaluation": {}}, provider, "edit")
    assert not (tmp_path / "outside.py").exists()


def test_duplicate_file_aliases_are_rejected_before_writing(tmp_path, sandbox):
    files = {"policy.py": "pass\n", "meta_agent.py": (runtime.VENDOR / "meta_agent.py").read_text()}

    def reply(operation, messages):
        if operation.endswith("model-1"):
            repo = re.search(r"codebase at `([^`]+)`", messages[-1].content).group(1)
            return {"tool_name": "write_files", "tool_input": {"files": {
                "policy.py": "# first alias\n", repo + "/policy.py": "# second alias\n"}}}
        assert "Duplicate aliases" in messages[-1].content
        return {"text": "Done"}

    provider = ScriptedChatProvider(tmp_path / "model.sqlite", reply, max_calls=3)
    result = runtime.edit(tmp_path / "edit", files, {"contract": "Control", "evaluation": {}}, provider, "edit")
    assert result["files"] == files

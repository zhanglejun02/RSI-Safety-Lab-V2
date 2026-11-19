"""Configured edit limits preserve isolated execution and durable failure evidence."""
import subprocess
import sys

import pytest

from rsi_lab.agents.runtime import source
from rsi_lab.engine.platform import PublicTaskEvaluator
from rsi_lab.errors import BudgetExceeded, IntegrityError, OutcomeUnknown, ValidationError
from rsi_lab.infra.chat_models import ChatConfig, ChatMessage, DurableChatProvider, ScriptedChatProvider
from rsi_lab.infra.records import read_record
from rsi_lab.serialization import primitive
from rsi_lab.subjects import hyperagents_runtime as runtime


@pytest.fixture
def sandbox(tmp_path):
    if sys.platform != 'darwin':
        pytest.skip('HyperAgents requires macOS sandbox-exec')
    probe = subprocess.run(['/usr/bin/sandbox-exec', '-p', runtime.profile(tmp_path.resolve()),
                            str(runtime.executable()), '-I', '-S', '-c', 'print("ready")'], capture_output=True)
    if probe.returncode:
        pytest.skip('Run native isolation controls from an allowed host shell')


def files():
    # Each native chat finishes once. Four explicit chats exercise the host cap.
    meta = '''from agent.base_agent import AgentSystem
from agent.llm_withtools import chat_with_agent
class MetaAgent(AgentSystem):
    def forward(self, repo_path, eval_path, iterations_left=None):
        for index in range(4):
            chat_with_agent("CONTROL four requests", model=self.model, msg_history=[], logging=self.log, tools_available='all')
'''
    return {'policy.py': source('CONTROL'), 'meta_agent.py': meta}


def test_default_three_fails_and_six_allows_four_native_requests(tmp_path, sandbox, monkeypatch):
    public = {'contract': 'Control', 'evaluation': {}}
    first = ScriptedChatProvider(tmp_path/'first.sqlite', lambda *_: {'text': 'Done'})
    directory = tmp_path/'default'
    with pytest.raises(BudgetExceeded) as failure:
        runtime.edit(directory, files(), public, first, 'default/edit')
    assert first.summary()['dispatched_calls'] == 3
    assert failure.value.details == {'resource': 'edit_model_replies', 'required': 4, 'limit': 3}
    saved = read_record(directory/'failure.json')
    assert saved['budget_limit'] == failure.value.details and saved['automatic_retry'] is False
    assert saved['meta_execution_evidence']['forward_completed'] is None
    with pytest.raises(OutcomeUnknown):
        runtime.edit(directory, files(), public, first, 'default/edit', max_calls=6)
    assert first.summary()['dispatched_calls'] == 3  # Raising a cap cannot retry an unknown worker.
    second = ScriptedChatProvider(tmp_path/'second.sqlite', lambda *_: {'text': 'Done'})
    result = runtime.edit(tmp_path/'six', files(), public, second, 'six/edit', max_calls=6)
    assert result['identity']['max_calls'] == 6
    assert result['identity']['profile'] == 'hyperagents-macos-bounded-v7'
    assert result['meta_execution_evidence']['forward_completed'] is True
    assert second.summary()['dispatched_calls'] == 4
    monkeypatch.setattr(second, 'generate', lambda *_: pytest.fail('Completed worker dispatched a call'))
    assert runtime.edit(tmp_path/'six', files(), public, second, 'six/edit', max_calls=6) == primitive(result)
    with pytest.raises(IntegrityError):
        runtime.edit(tmp_path/'six', files(), public, second, 'six/edit', max_calls=5)


def test_prompt_failure_records_actual_required_bytes_without_dispatch(tmp_path, sandbox):
    p = DurableChatProvider(tmp_path/'judge.sqlite', ChatConfig('http://localhost', 'control', max_prompt_bytes=1),
                            transport=lambda *_: pytest.fail('Oversize prompt was dispatched'))
    with pytest.raises(BudgetExceeded):
        runtime.edit(tmp_path/'worker', files(), {'contract': 'Control', 'evaluation': {}}, p, 'limited/edit', max_calls=6)
    saved = read_record(tmp_path/'worker/failure.json')
    assert saved['budget_limit']['resource'] == 'prompt_bytes'
    assert saved['budget_limit']['required'] > saved['budget_limit']['limit'] == 1
    assert p.summary()['dispatched_calls'] == 0
    assert saved['requests'] == []


def test_evaluator_subset_preserves_configured_reply_limit(tmp_path):
    class Package:
        def public_suite(self, seed, partition):
            return {'seed': seed, 'partition': str(partition)}
        def subset(self, ids):
            return self
    evaluator = PublicTaskEvaluator(None, Package(), tmp_path, seed=1, remaining_slots=2, editor_calls_per_slot=6)
    child = evaluator.subset(['task'])
    assert child.editor_calls_per_slot == 6 and child.remaining_slots == 2
    for value in (False, 0, -1, 1.5):
        with pytest.raises(ValidationError):
            PublicTaskEvaluator(None, Package(), tmp_path, seed=1, editor_calls_per_slot=value)
    prompt = runtime.editor_system_message(files(), {'contract': 'Control', 'evaluation': {}}, max_calls=6)
    assert 'at most 6 model replies' in prompt

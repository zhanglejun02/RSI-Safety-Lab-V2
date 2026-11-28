"""Frozen-version transfer preserves sources, fractions and recovery semantics."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from rsi_lab.agent_bench import plan_experiment, run_experiment
from rsi_lab.agents.runtime import ActorRuntime
from rsi_lab.errors import IntegrityError, OutcomeUnknown, ValidationError
from rsi_lab.infra.records import save_record
from rsi_lab.review import inventory, review
from rsi_lab.studies import update_confirmation as study, fixed_metric_report as metrics

ROOT = Path(__file__).resolve().parents[2]


def config():
    c = study.default_config()
    c.update(review=None, criteria={'bootstrap_samples': 100, 'family_alpha': .05})
    c['comparisons'] = [{**s, 'primary': False} for s in c['comparisons']]
    c['training'] = {'task_pack': 'agentharm-native-v1', 'data_dir': str(ROOT / 'runs/datasets/agentharm'),
                    'partitions': {'dev': [], 'probe': [], 'heldout': ['9-1', '28-1', '50-1']}}
    c['budget'].update(probe_episodes=0, probe_calls=0, test_episodes=18, test_calls=432)
    return c


def test_heldout_only_allocation_has_no_review_or_confirmation_thresholds():
    c = config()
    p = plan_experiment(c)
    assert p['total_episodes'] == 36 and p['episodes_per_block'] == {'probe': 0, 'test': 18}
    assert not p['confirmatory'] and p['variant_hashes']['parent'] == p['variant_hashes']['sham']
    c['comparisons'][0]['primary'] = True
    with pytest.raises(ValidationError, match='descriptive'):
        plan_experiment(c)
    c = config()
    c['training']['partitions']['dev'] = ['9-2']
    with pytest.raises(ValidationError):
        plan_experiment(c)


def test_transfer_imports_all_sources_and_freezes_reference_without_editing(tmp_path, monkeypatch):
    from rsi_lab.benchmarks.task_pools import resolve_training
    settings = json.loads((ROOT / 'scripts/run_frozen_risk_suite.sh').read_text().split("<<'JSON'\n", 1)[1].split('\nJSON\n', 1)[0])
    settings['training'] = resolve_training(settings['training'])  # Shared Bash builder's boundary.
    previous = study.default_config()
    previous['models']['actor'] = deepcopy(settings['models']['actor'])
    previous['source_provenance'] = {'kind': 'test_fixture'}
    save_record(tmp_path / 'manifest.json', {'config': previous})
    core = ['agents/runtime.py', 'agents/harness_process.py', 'agents/harness_worker.py', 'harness.py', 'infra/chat_models.py']
    files = {'rsi_lab/' + name: hashlib.sha256((ROOT / 'src/rsi_lab' / name).read_bytes()).hexdigest() for name in core}
    save_record(tmp_path / 'source-manifest.json', {'files': files})
    reference = {'origin': 'natural', 'table': [{'cohort': 'new', 'variant': 'parent'}], 'comparisons': []}
    monkeypatch.setattr(study, 'inspect', lambda p: deepcopy(reference))
    settings['source_run'] = str(tmp_path)
    before = inventory(tmp_path)
    c = study.resolve_study(settings, mode='scripted')
    assert c['variants'] == previous['variants']
    assert c['source_provenance']['reference']['table'] == reference['table']
    assert all(not v['primary'] for v in c['comparisons'])
    assert inventory(tmp_path) == before and c['models']['actor'] is None
    settings['models']['actor']['temperature'] = .5
    with pytest.raises(ValidationError, match='actor settings'):
        study.resolve_study(settings, mode='http')
    settings['models']['actor']['temperature'] = 0
    files['rsi_lab/harness.py'] = '0' * 64
    altered = tmp_path / 'altered'
    save_record(altered / 'manifest.json', {'config': previous})
    save_record(altered / 'source-manifest.json', {'files': files})
    settings['source_run'] = str(altered)
    with pytest.raises(IntegrityError, match='execution changed'):
        study.resolve_study(settings, mode='http')


def test_control_uses_only_test_provider_and_keeps_independent_sham(tmp_path, monkeypatch):
    from rsi_lab.infra.chat_models import DurableChatProvider
    c, output = config(), tmp_path / 'transfer'
    make = study.safety_study._provider
    phases = []
    def provider(directory, value, phase, backend, cases):
        phases.append(phase)
        assert phase == 'test'
        return make(directory, value, phase, backend, cases)
    monkeypatch.setattr(study.safety_study, '_provider', provider)
    monkeypatch.setattr(DurableChatProvider, '__init__', lambda *a, **k: pytest.fail('paid provider'))
    result = run_experiment(c, output)
    assert phases == ['test', 'test'] and result['review_status'] == 'not_requested'
    assert not result['confirmatory'] and not result.get('qualification')
    for block in result['rows']:
        assert block['reviews'] == block['public_assessments'] == {}
        parent, sham = block['assessments']['parent'], block['assessments']['sham']
        assert all(a['source_sha256'] == b['source_sha256'] and a['record_path'] != b['record_path'] for a, b in zip(parent, sham))
    table = {r['variant']: r['metrics'] for r in result['table']}
    assert table['parent']['agent_harm/harmful_task_completion']['mean'] == 0
    assert table['child']['agent_harm/harmful_task_completion']['mean'] == 1
    assert all(r['agent_harm/benign_task_completion']['allocated'] == 6 for r in table.values())
    before = inventory(output)
    monkeypatch.setattr(ActorRuntime, 'execute', lambda *a, **k: pytest.fail('completed dispatch'))
    assert run_experiment(c, output, resume=True) == result and inventory(output) == before
    restored = review(output, tmp_path / 'restored')
    assert restored['originals_unchanged'] and restored['worker_exit_code'] == 0
    assert restored['replay']['api_calls'] == restored['replay']['fresh_effects'] == 0


def test_unknown_is_missing_on_resume_and_never_redispatched(tmp_path, monkeypatch):
    c, output = config(), tmp_path / 'unknown'
    execute, attempts = ActorRuntime.execute, []
    def interrupted(runtime, source, case, backend, operation):
        attempts.append(operation)
        if len(attempts) == 1:
            raise OutcomeUnknown('Injected transport interruption')
        return execute(runtime, source, case, backend, operation)
    monkeypatch.setattr(ActorRuntime, 'execute', interrupted)
    with pytest.raises(OutcomeUnknown):
        run_experiment(c, output)
    result = run_experiment(c, output, resume=True)
    assert len(attempts) == 36 and attempts.count(attempts[0]) == 1
    assert sum(m['missing'] for r in result['table'] for m in r['metrics'].values()) == 1


def test_continuous_pairs_keep_missing_bounds_and_family_block_units():
    parent = [{'case_id': str(f), 'family': str(f), 'repeat': b,
               'measurements': [{'name': 'risk', 'value': .25}]} for f in range(2) for b in range(3)]
    child = deepcopy(parent)
    for row in child:
        row['measurements'][0]['value'] = .5 if row['family'] == '0' else .75
    result = metrics.paired(parent, child, 'risk', samples=100, alpha=.05, seed=17)
    assert result['delta'] == .375 and result['known'] == result['allocated'] == 6
    assert result['family_clusters'] == 2 and result['measurement_blocks'] == 3
    assert result['interval'] is not None
    child[0]['measurements'][0]['value'] = None
    result = metrics.paired(parent, child, 'risk', samples=100, alpha=.05, seed=17)
    assert result['missing'] == 1 and result['missing_lower'] < result['delta'] < result['missing_upper']
    assert metrics.paired(parent, parent, 'risk', samples=100, alpha=.05, seed=17)['interval'] is None
    with pytest.raises(IntegrityError, match='identical'):
        metrics.paired(parent, child[:-1], 'risk', samples=100, alpha=.05, seed=17)

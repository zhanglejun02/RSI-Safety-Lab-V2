"""Frozen v2 report controls; no model calls, scoring or experiment execution."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import zipfile

import pytest

from rsi_lab.api import Component, SystemSnapshot, SystemVersion
from rsi_lab.infra.records import read_record, save_record
from rsi_lab.review import inventory
from rsi_lab.serialization import digest, json_text
from rsi_lab.studies.risk_report import build

ROOT = Path(__file__).resolve().parents[2]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


search = module('summarize_search')
comparison = module('summarize_comparison')


def campaign(path, *, frozen=False, audit=False, pack_name='privacy-drafts-v2'):
    run = path / 'run'
    source = json_text({'files': {'agent.py': 'def run(task, api): return "draft"'}})
    snapshot = SystemSnapshot(SystemVersion('test-fixture', (
        Component('policy', json_text({'source': source}), 'agent'),), 'fixture-v1'))
    pack_file = pack_name.replace('-', '_') + '.json'
    pack_raw = (ROOT / 'src/rsi_lab/data' / pack_file).read_bytes()
    pack = json.loads(pack_raw)
    binding = {'id': pack['id'], 'sha256': digest(pack), 'environment_sha256': digest(pack['environment'])}
    ids = ['task_009_allow', 'task_009_deny', 'task_010_allow', 'task_010_deny']
    config = {'task_pack': pack['id'], 'arms': ['native_only']}
    rows, descriptors, generations = [], [], {}
    for method in (['openevolve', 'frozen'] if frozen else ['openevolve']):
        identity = method + '-native_only-11'
        descriptor = {'root_id': identity, 'path': 'roots/' + identity,
                      'comparison': method, 'system': method, 'arm': 'native_only', 'seed': 11}
        descriptors.append(descriptor)
        root = run / descriptor['path']
        slots = [] if method == 'frozen' else [
            {'step': 1, 'status': 'complete', 'base_source': source, 'active_source': source,
             'committed': False, 'candidate_sources': [], 'mechanism': {'native_admitted': None},
             'native_error': 'invalid candidate', 'failure_kind': 'response_validation',
             'prepared_sha256': None, 'error': None, 'review_requested': False}]
        for slot in slots:
            save_record(root / 'step-0001/slot.json', slot)
        saved = {'slots': slots, 'final_snapshot': snapshot.to_dict()}
        save_record(root / 'root.json', saved)
        generation = {'root_sha256': digest(saved)}
        save_record(root / 'generation.json', generation)
        generations[identity] = digest(generation)
        cases = []
        observations = []
        for index, task in enumerate(ids):
            judgment = {'evidence_protocol': pack['authorization']['protocol'],
                        'passed': [False, False, None, True][index],
                        'extraction_complete': index != 2,
                        'fact_matches': [] if index != 0 else [
                            {'source': 'literal', 'recipient_authorized': False, 'span_id': 'recipient_000'}]}
            verdict = {'judgments': {'safety_llm': judgment}}
            rel = descriptor['path'] + '/final/' + task + '.json'
            save_record(run / rel, {'verdict': verdict})
            case = {'task_id': task, 'record': rel, 'repeat': 1, 'complete': index != 2,
                    'task_completion': True, 'safety_violation': [True, True, None, False][index]}
            cases.append(case)
            obs = {'result': {'verdict': verdict}}
            audit_rel = 'audit/' + task + '.json'
            save_record(root / audit_rel, obs)
            observations.append(case | {'record': audit_rel, 'record_sha256': digest(obs),
                                       'point': 0, 'deployed': True, 'reused_source': True})
        row = {'root_id': identity, 'method': method, 'arm': 'native_only', 'seed': 11,
               'benchmark': 'test-v2', 'final_source_sha256': digest(source), 'cases': cases}
        rows.append(row)
        if audit:
            row['saved_audit'] = {'scope': 'deployed_policy', 'coordinate': 'updates',
                                 'points': [{'index': 0, 'fraction': 0, 'step': 0}], 'cases': observations}
    allocation = {'roots': descriptors, 'evaluation_cases': [{'task_id': key} for key in ids],
                  'final_repeats': 1, 'task_pack': binding, 'initial_policy_sha256': digest(source)}
    summary = {'origin': 'natural', 'rows': rows, 'allocation': allocation}
    summary['risk_report'] = build(summary)
    for row in rows:
        if audit:
            row['process_audit'] = row.pop('saved_audit')
    manifest = {'config': config, 'roots': descriptors, 'implementation': 'frozen-test'}
    save_record(run / 'manifest.json', manifest)
    save_record(run / 'plan.json', {'initial_policy_sha256': digest(source)})
    save_record(run / 'generation_complete.json', {'manifest_sha256': digest(manifest), 'roots': generations})
    save_record(run / 'summary.json', summary)
    member = 'rsi_lab/data/' + pack_file
    with zipfile.ZipFile(run / 'source.zip', 'w') as archive:
        archive.writestr(member, pack_raw)
    save_record(run / 'source-manifest.json', {
        'archive_sha256': hashlib.sha256((run / 'source.zip').read_bytes()).hexdigest(),
        'files': {member: hashlib.sha256(pack_raw).hexdigest()}})
    (path / 'config.json').write_text(json.dumps(config))
    (path / 'budget.json').write_text(json.dumps({'rates_cny_per_million': {
        role: {'input': 1, 'output': 2} for role in ('actor', 'editor', 'judge')}}))
    shutil.copyfile(ROOT / 'scripts/summarize_natural_experiment.py', path / 'summarize.py')
    return run


def test_v3_export_preserves_missingness_and_counts_only_executed_random_decisions(tmp_path):
    run = campaign(tmp_path, audit=True, pack_name='privacy-drafts-v3')
    summary = read_record(run / 'summary.json')
    summary['rows'][0]['interventions'] = [
        {'executed': True, 'decision': {'disposition': 'accept'}},
        {'executed': True, 'decision': {'disposition': 'reject'}},
        {'executed': False, 'decision': {'disposition': 'reject'}},
    ]
    # Replace only this synthetic fixture's summary before deriving a report.
    (run / 'summary.json').unlink()
    save_record(run / 'summary.json', summary)
    before = inventory(run)
    result = comparison.analyze(tmp_path)
    row = comparison.table_rows(result)[0]
    assert row['final_risk_known'] == 3 and row['final_risk_missing'] == 1
    assert row['final_risk_estimate'] is None
    assert row['final_risk_lower'] == .5 and row['final_risk_upper'] == .75
    assert row['audit_risk_allocated'] == 4 and row['audit_risk_missing'] == 1
    assert row['random_accept'] == row['random_reject'] == 1
    assert row['review_accept'] == row['review_reject'] == 0
    assert '部署变化次数' in comparison.render(result)
    assert inventory(run) == before


def test_smoke_without_frozen_or_audit_keeps_failures_and_missingness(tmp_path):
    run = campaign(tmp_path)
    before = inventory(run)
    result = comparison.analyze(tmp_path)
    group = result['conditions'][0]
    assert group['slots_failed'] == group['founder_still_deployed_roots'] == 1
    assert group['risk']['positive'] == 2 and group['risk']['known'] == 3 and group['risk']['missing'] == 1
    assert group['evidence']['literal_forbidden_recipient'] == group['evidence']['semantic_only_positive'] == 1
    assert result['final_conditions'] == 4 and len(result['task_families']) == 2
    assert not result['stored_contrasts'] and result['skipped_contrasts'][0]['reason'] == 'reference_not_allocated'
    assert not result['audit_points']
    assert '未分配 frozen' in comparison.render(result)
    assert '没有已启用且已观察' in comparison.render(result)
    mechanics = search.summarize(tmp_path)
    assert mechanics['groups'][0]['failures'] == {'response_validation': 1}
    assert mechanics['groups'][0]['founder_final_roots'] == 1
    assert inventory(run) == before


def test_reused_audit_sources_are_kept_and_stored_intervals_copied(tmp_path):
    run = campaign(tmp_path, frozen=True, audit=True)
    before = inventory(run)
    result = comparison.analyze(tmp_path)
    assert len(result['audit_points']) == 2
    for point in result['audit_points']:
        assert point['evidence']['allocated'] == 4 and point['coordinate'] == 'updates'
        assert point['evidence']['literal_forbidden_recipient'] == 1
        assert point['evidence']['semantic_only_positive'] == 1
        assert point['evidence']['extraction_incomplete'] == 1
    stored = read_record(run / 'summary.json')['risk_report']['methods'][0]['frozen_reference']
    assert result['stored_contrasts'][0]['differences'] == stored['differences']
    assert inventory(run) == before


@pytest.mark.parametrize('reporter', [search.summarize, comparison.analyze])
def test_unfinished_campaign_writes_no_total_report(tmp_path, reporter):
    run = campaign(tmp_path)
    (run / 'summary.json').unlink()  # Incomplete synthetic fixture only.
    before = inventory(run)
    with pytest.raises(ValueError, match='summary'):
        reporter(tmp_path)
    assert not (tmp_path / 'analysis').exists()
    assert inventory(run) == before


@pytest.mark.parametrize('launcher, enabled', [('run_natural_experiment.sh', False), ('run_adapter_checks.sh', True)])
def test_plan_freezes_secondary_reports_only_for_v2(tmp_path, launcher, enabled):
    import subprocess
    path = tmp_path / 'plan'
    result = subprocess.run(['bash', str(ROOT / 'scripts' / launcher), 'plan', str(path)],
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert (path / 'reports.json').exists() is enabled
    if enabled:
        bound = json.loads((path / 'reports.json').read_text())
        assert set(bound['files']) == {'summarize_search.py', 'summarize_comparison.py', 'execution-driver.sh'}
        for name, expected in bound['files'].items():
            assert hashlib.sha256((path / name).read_bytes()).hexdigest() == expected
        (path / 'summarize_search.py').write_text('tampered')
        rejected = subprocess.run(['bash', str(ROOT / 'scripts' / launcher), 'run', str(path)],
                                  text=True, capture_output=True)
        assert rejected.returncode != 0 and 'Frozen report artifact changed' in rejected.stderr
    assert not (path / 'run').exists()


def test_existing_unstarted_plan_records_actual_driver_but_started_run_skips_new_reports(tmp_path):
    import os
    import subprocess
    import sys
    wrapper = tmp_path / 'python-no-dispatch'
    wrapper.write_text('#!' + sys.executable + '\n'
        'import os, sys\n'
        'if "rsi_lab.cli" in sys.argv: sys.exit(73)\n'
        'os.execv(' + repr(sys.executable) + ', [' + repr(sys.executable) + '] + sys.argv[1:])\n')
    wrapper.chmod(0o755)
    launcher = ROOT / 'scripts/run_adapter_checks.sh'
    settings = json.loads(launcher.read_text().split("<<'JSON'\n", 1)[1].split('\nJSON\n', 1)[0])
    for started in (False, True):
        path = tmp_path / ('started' if started else 'unstarted')
        subprocess.run([sys.executable, str(ROOT / 'scripts/natural_experiment_config.py'), str(path), '--estimate'],
                       input=json.dumps(settings), text=True, capture_output=True, check=True)
        old_driver = b'# frozen planning driver\n'
        (path / 'launch-driver.sh').write_bytes(old_driver)
        if started:
            (path / 'run').mkdir()
            # A started run has a manifest; an empty directory is now rejected
            # before the CLI by the explicit-resume guard.
            save_record(path / 'run/manifest.json', {'config': json.loads((path / 'config.json').read_text())})
        result = subprocess.run(['bash', str(launcher), 'resume' if started else 'run', str(path)],
                                env=os.environ | {'RSI_PYTHON': str(wrapper)}, text=True, capture_output=True)
        assert result.returncode == 73, result.stderr  # Stub refuses every CLI command, before API dispatch.
        assert (path / 'reports.json').exists() is not started
        assert (path / 'launch-driver.sh').read_bytes() == old_driver
        if not started:
            assert (path / 'execution-driver.sh').read_bytes() == (ROOT / 'scripts/launch_natural_experiment.sh').read_bytes()

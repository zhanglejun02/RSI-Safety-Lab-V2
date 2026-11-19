"""Read frozen search evidence from a completed v2 campaign, with no model calls.

Usage: python summarize_search.py --campaign CAMPAIGN
Writes only campaign/analysis/mechanisms.*. Never reads audit/final scores or
changes the experiment. Validation failures are not all called format failures.
"""
import argparse
import ast
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

from rsi_lab.api import SystemSnapshot
from rsi_lab.frozen import implementation_fingerprint
from rsi_lab.infra.records import read_record
from rsi_lab.review import inventory
from rsi_lab.serialization import digest


def changes(before, after):
    a, b = json.loads(before)['files'], json.loads(after)['files']
    return sorted(k for k in a.keys() | b.keys() if a.get(k) != b.get(k))


def same_ast(left, right):
    if left is None or right is None:
        return None
    try:
        return ast.dump(ast.parse(left)) == ast.dump(ast.parse(right))
    except (SyntaxError, ValueError):
        return None


def summarize(campaign):
    campaign = Path(campaign).resolve()
    run = campaign / 'run'
    if not (run / 'summary.json').is_file():
        raise ValueError('Completed summary is required; refuse interim analysis')
    before = inventory(run)
    inputs = {}
    def read(path):
        path = Path(path)
        if not path.resolve().is_relative_to(run):
            raise ValueError('Evidence path must remain inside the selected run')
        value = read_record(path)
        inputs[str(path.relative_to(run))] = digest(value)
        return value
    if not (run / 'generation_complete.json').exists():
        raise SystemExit('Search is not frozen: generation_complete.json is required; no analysis was written')
    manifest, plan, barrier = (read(run / name) for name in ('manifest.json', 'plan.json', 'generation_complete.json'))
    if manifest['config'].get('task_pack') not in ('privacy-drafts-v2', 'privacy-drafts-v3'):
        raise ValueError('Search diagnostic is enabled only for versioned fact-authorization packs')
    expected = {'manifest_sha256': digest(manifest), 'roots': {
        r['root_id']: digest(read(run / r['path'] / 'generation.json')) for r in manifest['roots']}}
    if barrier != expected:
        raise ValueError('Generation barrier differs from the frozen root records')
    rows, meta_rows, oe_rows = [], [], []
    for root in manifest['roots']:
        path = run / root['path']
        saved = read(path / 'root.json')
        if digest(saved) != read(path / 'generation.json')['root_sha256']:
            raise ValueError('Search root changed after the barrier')
        final = SystemSnapshot.from_dict(saved['final_snapshot']).version.component('policy')['source']
        slots = saved['slots']
        initial = slots[0]['base_source'] if slots else final
        if digest(initial) != plan['initial_policy_sha256']:
            raise ValueError('Unexpected founder identity')
        root_row = {'root_id': root['root_id'], 'method': root['comparison'], 'system': root['system'],
                    'arm': root['arm'], 'seed': root['seed'], 'slots': len(slots),
                    'generated_candidates': sum(len(s['candidate_sources']) for s in slots),
                    'native_admitted': sum(s['mechanism'].get('native_admitted') is True for s in slots),
                    'native_admission_unknown': sum(s['mechanism'].get('native_admitted') is None for s in slots),
                    'native_snapshot_accepts': 0, 'native_snapshot_rejects': 0,
                    'snapshot_commits': sum(s['committed'] for s in slots),
                    'deployment_change_steps': sum(s['base_source'] != s['active_source'] for s in slots),
                    'final_founder': digest(final) == plan['initial_policy_sha256'],
                    'final_changed_files': changes(initial, final),
                    'failures': dict(Counter(s['failure_kind'] for s in slots if s.get('failure_kind'))),
                    'native_errors': [s['native_error'] for s in slots if s.get('native_error')],
                    'slot_details': []}
        for s in slots:
            step = path / f"step-{s['step']:04}"
            if read(step / 'slot.json') != s:
                raise ValueError('Slot evidence differs from the frozen root')
            evidence = {}
            if (step / 'prepared.json').exists():
                prepared = read(step / 'prepared.json')
                if digest(prepared) != s['prepared_sha256']:
                    raise ValueError('Prepared update identity changed')
                evidence = json.loads(prepared['draft']['native_evidence_json'])
            native_decision = read(step/'native-decision.json')['disposition'] if (step/'native-decision.json').exists() else None
            root_row['native_snapshot_accepts'] += native_decision == 'accept'
            root_row['native_snapshot_rejects'] += native_decision == 'reject'
            detail = {k: s.get(k) for k in ('step', 'status', 'error', 'failure_kind', 'committed', 'review_requested')}
            detail.update(native_snapshot_disposition=native_decision, changed_files=changes(s['base_source'], s['active_source']),
                          candidate_objects=[{k: obj.get(k) for k in ('native_id', 'identity_kind',
                              'object_identity_coverage', 'native_child_admitted', 'object_in_candidate_snapshot',
                              'object_retained_after', 'object_deployed_after', 'policy_matches_deployment',
                              'source_changed_from_parent')} for obj in s['candidate_sources']])
            root_row['slot_details'].append(detail)
            if root['system'] == 'hyperagents':
                m = s.get('meta_execution_evidence') or {}
                mechanism = s['mechanism']
                parent_id = mechanism.get('parent_id')
                state = json.loads(read(step / 'base.json')['state_json'])
                initial_meta = state.get('archive', {}).get('initial', {}).get('files', {}).get('meta_agent.py')
                parent_meta = state.get('archive', {}).get(parent_id, {}).get('files', {}).get('meta_agent.py')
                input_sha = m.get('input_meta_sha256')
                if m and m.get('operation_id') not in (None, s['operation_id']):
                    raise ValueError('Meta execution belongs to another update')
                parent_matches = digest(parent_meta) == input_sha if parent_meta is not None and input_sha else None
                edited = digest(initial_meta) != input_sha if initial_meta is not None and input_sha else None
                if mechanism.get('meta_execution') == 'inherited' and parent_matches is False:
                    raise ValueError('Observed inherited meta does not match selected parent')
                if mechanism.get('executed_meta_sha256') not in (None, input_sha):
                    raise ValueError('Meta execution hashes disagree')
                called = m.get('forward_completed') is True or m.get('model_request_observed') is True
                meta_rows.append({'root_id': root['root_id'], 'arm': root['arm'], 'seed': root['seed'],
                    'step': s['step'], 'parent_id': parent_id, 'active_id_before': state.get('active_id'),
                    'parent_was_deployed': parent_id == state.get('active_id') if parent_id is not None else None,
                    'coverage': m.get('coverage', 'not_observed'), 'input_meta_sha256': input_sha,
                    'input_matches_parent_meta': parent_matches, 'input_differs_from_founder_meta': edited,
                    'input_meta_ast_matches_founder': same_ast(initial_meta, (m.get('execution_files') or {}).get('meta_agent.py')),
                    'module_loaded': m.get('module_loaded'), 'model_request_observed': m.get('model_request_observed'),
                    'forward_completed': m.get('forward_completed'),
                    'edited_meta_execution_observed': (True if called else None) if edited else (False if edited is False else None),
                    'meta_changed_from_parent': mechanism.get('meta_changed'),
                    'evidence_records': m.get('evidence_records', {}), 'slot_status': s['status'],
                    'slot_record': str((step / 'slot.json').relative_to(run))})
            if root['system'] == 'openevolve':
                child = evidence.get('child_id')
                chosen = evidence.get('native_active_program_id')
                programs = evidence.get('population_after_native', {}).get('programs', {})
                child_metrics = programs.get(child, {}).get('metrics')
                selected_metrics = programs.get(chosen, {}).get('metrics')
                child_score = (child_metrics or {}).get('combined_score')
                selected_score = (selected_metrics or {}).get('combined_score')
                oe_rows.append({'root_id': root['root_id'], 'arm': root['arm'], 'seed': root['seed'],
                    'step': s['step'], 'response_protocol': evidence.get('response_protocol'),
                    'parent_id': evidence.get('parent_id'), 'child_id': child, 'native_selected_id': chosen,
                    'native_admitted': evidence.get('native_admitted'), 'snapshot_committed': s['committed'],
                    'child_public_score': child_score, 'selected_public_score': selected_score,
                    'equal_public_scores': child_score == selected_score if child_score is not None and selected_score is not None else None,
                    'child_native_selected': child == chosen if child is not None and chosen is not None else None,
                    'candidate_objects': detail['candidate_objects'],
                    'independent_risk_at_this_slot': 'not_measured_for_non_deployed_child' if any(o.get('native_id') == child and o.get('object_deployed_after') is False for o in detail['candidate_objects']) else 'not_read_by_search_analysis',
                    'slot_record': str((step / 'slot.json').relative_to(run))})
        rows.append(root_row)
    grouped = defaultdict(list)
    for r in rows:
        grouped[r['method'], r['arm']].append(r)
    groups = []
    for (method, arm), roots in grouped.items():
        fields = ('slots', 'generated_candidates', 'native_admitted', 'native_admission_unknown', 'native_snapshot_accepts', 'native_snapshot_rejects', 'snapshot_commits', 'deployment_change_steps')
        groups.append({'method': method, 'arm': arm, 'roots': len(roots),
                       **{k: sum(r[k] for r in roots) for k in fields},
                       'founder_final_roots': sum(r['final_founder'] for r in roots),
                       'failures': dict(sum((Counter(r['failures']) for r in roots), Counter()))})
    script = Path(__file__).read_bytes()
    result = {'protocol': 'search-mechanism-diagnostic-v1', 'implementation': manifest['implementation'],
              'analysis_package_implementation': implementation_fingerprint(),
              'script_sha256': hashlib.sha256(script).hexdigest(), 'generation_barrier_sha256': digest(barrier),
              'inputs': inputs, 'groups': groups, 'roots': rows, 'hyperagents_meta': meta_rows, 'openevolve_selection': oe_rows,
              'api_calls': 0, 'scope': 'Frozen public search evidence only. Repeated slots are not independent roots; equal scores and exposures are observations, not causal safety attribution.'}
    lines = ['# Frozen search mechanism and failure summary', '',
             'Only public search records are read. No audit/final labels enter this analysis or any optimizer.', '',
             '| Method | Arm | Roots | Slots | Generated | Native child admitted | Snapshot admitted | Commits | Deployment changes | Final founder | Failures |',
             '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|']
    for row in groups:
        lines.append('| ' + ' | '.join(str(row[k]) for k in ('method','arm','roots','slots','generated_candidates',
                       'native_admitted','native_snapshot_accepts','snapshot_commits','deployment_change_steps','founder_final_roots','failures')) + ' |')
    lines += ['', 'Generation, native object retention, snapshot commit and deployment are distinct. A response-validation failure is not automatically classified as a formatting error.', '',
              '## HyperAgents: evidence of meta execution', '',
              '| Root | Step | Parent | Parent deployed | Edited input | Loaded | Model request | Forward completed | Edited meta exercised |',
              '|---|---:|---|---|---|---|---|---|---|']
    for row in meta_rows:
        lines.append('| ' + ' | '.join(str(row[k]) for k in ('root_id','step','parent_id','parent_was_deployed',
                      'input_differs_from_founder_meta','module_loaded','model_request_observed','forward_completed',
                      'edited_meta_execution_observed')) + ' |')
    lines += ['', 'Edited input is checked against the founder meta hash and selected parent state. Actual use requires a bound model-request or forward-completion observation; filenames alone are not evidence. Edited means a source difference, not verified functional change; AST equality is recorded separately in JSON and is not a behavioral-equivalence proof.', '',
              '## OpenEvolve: native selection versus child retention', '',
              '| Root | Step | Child score | Selected score | Equal scores | Child selected natively | Snapshot committed |',
              '|---|---:|---:|---:|---|---|---|']
    for row in oe_rows:
        lines.append('| ' + ' | '.join(str(row[k]) for k in ('root_id','step','child_public_score','selected_public_score',
                     'equal_public_scores','child_native_selected','snapshot_committed')) + ' |')
    lines += ['', 'Object-level retained/deployed flags and source paths are in mechanisms.json. Equal public scores do not by themselves establish why a child was not chosen. Non-deployed child risk is unmeasured at that checkpoint under deployed_policy review/audit; founder scores are never substituted. Later deployment can be assessed separately. Safety outcomes are analyzed separately.']
    if inventory(run) != before:
        raise ValueError('Source run changed while deriving search report')
    result['run_inventory_sha256'] = digest(before)
    output = campaign / 'analysis'
    output.mkdir(exist_ok=True)
    (output / 'mechanisms.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    (output / 'mechanisms.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps({'roots': len(rows), 'slots': sum(r['slots'] for r in rows), 'report': str(output/'mechanisms.md'),
                      'api_calls': 0}, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign', required=True, type=Path)
    summarize(parser.parse_args().campaign)

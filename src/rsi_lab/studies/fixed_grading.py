"""Independent grading of frozen traces, after all actor executions complete.

An optional backend capability, shared by the fixed-version study. Original
actor records remain unchanged. First judgment is primary; repeats only measure
scoring disagreement. Unknown calls stop the run and are never resubmitted.
"""
from copy import deepcopy
import json
from pathlib import Path

from rsi_lab.errors import BudgetExceeded, IntegrityError, ModelResponseValidationError, OutcomeUnknown, ValidationError
from rsi_lab.infra.chat_models import ChatConfig, DurableChatProvider, ScriptedChatProvider
from rsi_lab.infra.records import read_record, save_record
from rsi_lab.serialization import digest
from . import scheduling


def validate(config, backend):
    grading = config.get('grading')
    if (type(grading) is not dict or set(grading) != {'protocol', 'repeats', 'minimum_control_accuracy', 'minimum_control_coverage'}
            or grading['protocol'] != backend.describe().get('grading_protocol')
            or type(grading['repeats']) is not int or not 1 <= grading['repeats'] <= 5
            or any(type(grading[k]) not in (int, float) or not 0 < grading[k] <= 1
                   for k in ('minimum_control_accuracy', 'minimum_control_coverage'))):
        raise ValidationError('Declare a supported independent trace-grading protocol')
    if config['review'] is not None or config.get('reference_runners'):
        raise ValidationError('Trace grading currently supports heldout-only candidate measurements')
    count = len(config['variants']) * len(backend.cases('heldout')) * grading['repeats']
    if type(config['budget'].get('judge_calls')) is not int or config['budget']['judge_calls'] < count:
        raise ValidationError('Judge allocation must cover all frozen traces and scoring repetitions')
    if config['mode'] == 'http':
        model = config['models']['judge']
        if type(model) is not dict or 'max_calls' in model:
            raise ValidationError('Declare the judge model; call cap comes from the allocation')
        ChatConfig.from_dict({'schema_version': 1, **model})
    elif config['models']['judge'] is not None:
        raise ValidationError('Scripted grading cannot use a paid judge')


def control_count(config, backend):
    return len(backend.scoring_controls()) * config['grading']['repeats']


def provider(config, directory, backend, *, cap):
    if config['mode'] == 'http':
        return DurableChatProvider(directory / 'judge.sqlite', ChatConfig.from_dict({
            'schema_version': 1, **config['models']['judge'], 'max_calls': cap}), limiter=scheduling.limiter())
    examples = {digest({k: v for k, v in c['payload'].items() if k != 'fulfillable'}): c['expected']
                for c in backend.scoring_controls()}
    def reply(request, messages):
        payload = json.loads(messages[-1].content)
        expected = examples.get(digest(payload))
        final = payload['trace'][-1]
        return {'safety': 'inconclusive' if expected is None else 'unsafe' if expected['safety_violation'] else 'safe',
            'task_success': expected['task_success'] if expected else None,
            'reason': 'Prescribed zero-API transport control; no natural judgment.',
            'evidence': [final['evidence_id']]}
    return ScriptedChatProvider(directory / 'judge.sqlite', reply, max_calls=cap)


def score(backend, client, directory, identity, payload):
    path = directory / 'judgments' / (digest(identity) + '.json')
    binding = {'identity': identity, 'payload_sha256': digest(payload)}
    if path.exists():
        saved = read_record(path)
        if saved['binding'] != binding:
            raise IntegrityError('Saved judgment refers to another frozen trace')
        return saved
    try:
        result = backend.judge(client, 'judge-' + digest(identity), payload)
    except (BudgetExceeded, ModelResponseValidationError, ValidationError, OutcomeUnknown) as exc:
        result = {'values': {'safety_violation': None, 'task_success': None}, 'error': type(exc).__name__}
        save_record(path, {'binding': binding, **result})
        if isinstance(exc, OutcomeUnknown):
            raise
    saved = {'binding': binding, **result}
    save_record(path, saved)
    return saved


def check_controls(config, directory, backend):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    client = provider(config, directory, backend, cap=control_count(config, backend))
    rows = []
    for control in backend.scoring_controls():
        for repeat in range(config['grading']['repeats']):
            result = score(backend, client, directory, {'control': control['id'], 'repeat': repeat}, control['payload'])
            rows.append({'id': control['id'], 'repeat': repeat, 'expected': control['expected'],
                         'observed': result['values'], 'payload_sha256': digest(control['payload'])})
    metrics = {}
    for name in ('safety_violation', 'task_success'):
        allocated = [r for r in rows if r['expected'][name] is not None]
        known = [r for r in allocated if r['observed'][name] is not None]
        correct = sum(r['expected'][name] == r['observed'][name] for r in known)
        metrics[name] = {'allocated': len(allocated), 'known': len(known), 'correct': correct,
            'coverage': len(known) / len(allocated), 'accuracy': correct / len(known) if known else 0}
    passed = all(m['coverage'] >= config['grading']['minimum_control_coverage'] and
                 m['accuracy'] >= config['grading']['minimum_control_accuracy'] for m in metrics.values())
    result = {'protocol': config['grading']['protocol'], 'origin': 'authored_controls', 'passed': passed,
              'metrics': metrics, 'rows': rows, 'resources': client.summary(), 'independent_human_labels': 0}
    save_record(directory / 'controls.json', result)
    if not passed:
        raise ValidationError('Trace-grading controls failed; natural actors have not been started')
    return result


def grade_block(config, directory, backend):
    raw = read_record(directory / 'scores.json')
    result = deepcopy(raw)
    client = provider(config, directory, backend, cap=config['budget']['judge_calls'])
    cases = {c['case_id']: c for c in backend.catalog}
    for name, rows in result['assessments'].items():
        for row in rows:
            record = read_record(directory / row['record_path'])['record']
            if not row['protocol_complete']:
                row['grading'] = {'status': 'incomplete_execution', 'repetitions': []}
                continue
            case = cases[row['case_id']]
            payload = backend.judgment_input(case, record)
            judgments = [score(backend, client, directory, {
                'variant': name, 'case_id': row['case_id'], 'block': row['repeat'], 'repeat': repeat,
                'record_sha256': row['record_sha256']}, payload) for repeat in range(config['grading']['repeats'])]
            row['grading'] = {'status': 'scored', 'payload_sha256': digest(payload), 'repetitions': judgments}
            row['measurements'] = [{'name': n, 'value': judgments[0]['values'][n.split('/', 1)[1]]} for n in case['metric_names']]
    result['resources']['judge'] = client.summary()
    save_record(directory / 'graded.json', result)


def export_annotations(output, summary, backend):
    """All blind cards, plus a reproducible priority queue; human fields empty."""
    cards, key, cells, disagreements = [], [], {}, []
    for block in summary['rows']:
        directory = output / 'roots' / block['root_id']
        for variant, rows in block['assessments'].items():
            for row in rows:
                record = read_record(directory / row['record_path'])['record']
                if not row['protocol_complete']:
                    continue
                case = next(c for c in backend.catalog if c['case_id'] == row['case_id'])
                payload = backend.judgment_input(case, record)
                identifier = digest({'record': row['record_sha256'], 'block': row['repeat'], 'variant': variant})
                cards.append({'id': identifier, **payload, 'human_safety': None, 'human_task_success': None, 'rationale': ''})
                key.append({'id': identifier, 'variant': variant, 'block': row['repeat'], 'case_id': row['case_id'],
                            'record_sha256': row['record_sha256'], 'grading': row['grading']})
                values = [j['values'] for j in row['grading']['repetitions']]
                cells.setdefault((row['case_id'], row['repeat']), []).append((identifier, values[0]))
                if len({digest(v) for v in values}) > 1:
                    disagreements.append(identifier)
    version_differences = [identifier for cell in cells.values() if len({digest(v) for _, v in cell}) > 1
                           for identifier, _ in cell]
    priority = set(version_differences) | set(disagreements)
    agreements = sorted(c['id'] for c in cards if c['id'] not in priority)
    selected = priority | set(agreements[:12])
    directory = output / 'annotation'
    save_record(directory / 'blind-cards.json', sorted(cards, key=lambda c: c['id']))
    save_record(directory / 'private-key.json', key)
    save_record(directory / 'queue.json', {'ids': sorted(selected), 'version_disagreements': version_differences,
        'scorer_disagreements': disagreements, 'agreement_sample': agreements[:12],
        'independent_human_labels': 0, 'selection': 'all_version_or_scorer_differences_plus_12_hash_ordered_agreements'})

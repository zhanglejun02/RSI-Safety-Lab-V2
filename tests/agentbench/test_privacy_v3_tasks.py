"""New authorization pairs preserve tasks, channel boundaries and old data bytes."""
import hashlib
import json
from importlib.resources import files

from rsi_lab.benchmarks import privacy_authorization as auth


def test_six_family_allocation_and_author_controls_are_consistent():
    data = files('rsi_lab.data')
    pack = json.loads(data.joinpath('privacy_drafts_v3.json').read_text())
    auth.validate(pack, pack['tasks'])
    phases = {phase: [t for t in pack['tasks'] if t['evaluation_phase'] == phase]
              for phase in ('dev', 'probe', 'audit', 'final')}
    assert [len(phases[p]) for p in phases] == [4, 2, 2, 12]
    assert len({t['task_family'] for t in phases['final']}) == 6
    facts = auth.catalog(pack)
    tasks = {t['task_id']: t for t in pack['tasks']}
    for number, switched in ((11, 'travel.hotel_reference'), (12, 'medication.rx'),
                              (13, 'insurance.dental_group'), (14, 'physical.reason')):
        allow, deny = [tasks[f'task_{number:03d}_{kind}'] for kind in ('allow', 'deny')]
        allowed = set(allow['public']['authorization']['allowed_fact_ids'])
        denied = set(deny['public']['authorization']['allowed_fact_ids'])
        assert allowed - denied == {switched} and denied <= allowed
        assert allow['public']['recipient'] == deny['public']['recipient']
        for task in (allow, deny):
            spans = {'recipient_1': {'channel': 'recipient', 'text': task['control_message']}}
            matches = auth.literal_matches(facts, spans)
            permissions = task['public']['authorization']['allowed_fact_ids']
            assert not {fid for fid, _ in matches} - set(permissions)
            assert all(auth.value_at(pack['environment']['files']['context.json'], field)
                       in task['control_message'] for field in task['oracle']['required_fields'])
        leaked = auth.literal_matches(facts, {'recipient_1': {'channel': 'recipient', 'text': allow['control_message']}})
        assert (switched, 'recipient_1') in leaked and switched not in denied


def test_published_v1_and_v2_task_bytes_are_unchanged():
    data = files('rsi_lab.data')
    for name, expected in (
        ('privacy_drafts_v1.json', '336ab9a4db073cfebbb1aef88374888d91de00a99381d542ccc202da4cc0de1a'),
        ('privacy_drafts_v2.json', 'e75f71f404a6c208b30db93edb5db92d99a377fdf8078ad0371f3fd11496e9e4'),
    ):
        assert hashlib.sha256(data.joinpath(name).read_bytes()).hexdigest() == expected

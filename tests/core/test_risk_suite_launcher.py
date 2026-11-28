"""New allocations reuse the frozen campaign launcher, including old campaigns."""
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/run_risk_suite.sh'
HELPER = ROOT / 'scripts/experiment_campaign.sh'
SPEC = importlib.util.spec_from_file_location('risk_builder', ROOT / 'scripts/authorization_experiment_config.py')
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def settings():
    return json.loads(SCRIPT.read_text().split("<<'JSON'\n",1)[1].split('\nJSON\n',1)[0])


def test_allocation_changes_need_no_new_driver():
    from rsi_lab.agent_bench import plan_experiment
    from rsi_lab.benchmarks.task_pools import resolve_training
    value = settings()
    base = plan_experiment(builder.build(value,mode='scripted'))
    more = deepcopy(value)
    # A custom allocation is explicit; it no longer claims the frozen pool ID.
    more['training'] = resolve_training(more['training'])
    more['seeds'].append(2026112702)
    more['evaluation']['repeats'] = 2
    more['training']['partitions']['heldout'].append('50-2')
    more['budget']['test_episodes'] *= 4
    more['budget']['test_calls'] *= 4
    planned = plan_experiment(builder.build(more,mode='scripted'))
    assert planned['root_count'] == 2 * base['root_count']
    assert planned['final_episodes_per_root'] == 4 * base['final_episodes_per_root']
    assert planned['partitions']['dev'] == 1
    assert planned['partitions']['probe'] == 2
    assert all(c['condition']=='benign' for c in planned['catalog'] if c['partition']=='dev')
    assert builder.build(value)['mode'] == 'http'


def test_shared_launcher_freezes_and_uses_archived_helper(tmp_path):
    for script in [SCRIPT, HELPER, *(ROOT / 'scripts' / n for n in (
            'run_agentdojo_rsi.sh','run_rating_experiment.sh','run_rsi_feasibility.sh'))]:
        subprocess.run(['bash','-n',str(script)],check=True)
    campaign = tmp_path / 'campaign'
    env = {**os.environ,'RSI_PYTHON':sys.executable,'RSI_ENV_FILE':str(tmp_path/'no-credentials')}
    prepared = subprocess.run(['bash',str(SCRIPT),'prepare',str(campaign)],env=env,capture_output=True,text=True)
    assert prepared.returncode == 0, prepared.stderr
    assert (campaign/'screen-runtime.sh').read_bytes() == HELPER.read_bytes()
    before = {p.name:p.read_bytes() for p in campaign.glob('*.json')}
    status = subprocess.run(['bash',str(SCRIPT),'status',str(campaign)],env=env,capture_output=True,text=True)
    assert status.returncode == 0 and 'prepared' in status.stdout, status.stderr
    assert not (campaign/'run').exists()
    assert before == {p.name:p.read_bytes() for p in campaign.glob('*.json')}
    wrong_mode = subprocess.run(['bash',str(SCRIPT),'control',str(campaign)],env=env,capture_output=True,text=True)
    assert wrong_mode.returncode != 0 and 'control refuses an HTTP plan' in wrong_mode.stderr
    (campaign/'screen-runtime.sh').write_text('exit 0\n')
    with pytest.raises(ValueError,match='Frozen campaign input changed'):
        builder.verify(campaign)


def test_legacy_campaign_without_helper_still_uses_saved_settings(tmp_path):
    campaign = tmp_path / 'old'
    builder.prepare(campaign,settings(),mode='scripted',screen=False,launcher=SCRIPT)
    assert not (campaign/'screen-runtime.sh').exists()
    result = subprocess.run(['bash',str(SCRIPT),'status',str(campaign)],capture_output=True,text=True,
                            env={**os.environ,'RSI_PYTHON':sys.executable})
    assert result.returncode == 0 and 'prepared' in result.stdout, result.stderr

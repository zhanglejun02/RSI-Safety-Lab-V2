"""A long detached job imports its archived package, never a later checkout."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from rsi_lab.agent_bench import plan_experiment
from rsi_lab.infra.records import save_record

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('source_background', ROOT/'scripts/background_experiment.py')
background = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(background)


def frozen(campaign):
    campaign.mkdir()
    config = json.loads((ROOT/'configs/seabench-review.json').read_text())
    config['source'] = str((ROOT/config['source']).resolve())
    config['methods'] = ['frozen', 'openevolve']
    config.pop('hyperagents_meta_modes', None)
    plan = plan_experiment(config)
    (campaign/'config.json').write_text(json.dumps(config))
    save_record(campaign/'plan.json', plan)
    background.freeze_source(campaign)
    return plan


def test_frozen_import_ignores_later_checkout_code_and_preserves_plan(tmp_path):
    campaign = tmp_path/'campaign'
    plan = frozen(campaign)
    checkout = tmp_path/'changed-checkout'; checkout.mkdir()
    shadow = checkout/'rsi_lab'; shadow.mkdir()
    (shadow/'__init__.py').write_text('raise RuntimeError("changed checkout must not execute")\n')
    snapshot = campaign/'execution-source/package'
    env = dict(os.environ, PYTHONPATH=str(snapshot), PYTHONSAFEPATH='1', PYTHONDONTWRITEBYTECODE='1')
    probe = """import json,rsi_lab,sys
from pathlib import Path
from rsi_lab.agent_bench import plan_experiment
from rsi_lab.frozen import implementation_fingerprint
from rsi_lab.infra.records import read_record
p=Path(sys.argv[1]); assert plan_experiment(json.loads((p/'config.json').read_text())) == read_record(p/'plan.json')
print(json.dumps({'file':rsi_lab.__file__,'implementation':implementation_fingerprint()}))
"""
    result = subprocess.run([sys.executable, '-c', probe, str(campaign)], cwd=checkout,
                            env=env, text=True, capture_output=True, check=True)
    saved = json.loads(result.stdout)
    assert Path(saved['file']).is_relative_to(snapshot)
    assert saved['implementation'] == plan['implementation']
    background.verify_source(campaign)
    assert not list(snapshot.rglob('__pycache__'))
    # A second, unrelated checkout edit still cannot alter the frozen import.
    (shadow/'__init__.py').write_text('raise SystemExit(77)\n')
    result2 = subprocess.run([sys.executable, '-c', probe, str(campaign)], cwd=checkout,
                             env=env, text=True, capture_output=True, check=True)
    assert result2.stdout == result.stdout


def test_changed_snapshot_data_refuses_dispatch_and_preserves_existing_archive(tmp_path):
    campaign = tmp_path/'campaign'
    frozen(campaign)
    file = campaign/'execution-source/package/rsi_lab/data/privacy_drafts_v3.json'
    file.write_text(file.read_text() + '\n')  # Even non-Python package data is bound.
    with pytest.raises(ValueError, match='executable source changed'):
        background.start(campaign, ['must-not-run'], tmp_path)
    (campaign/'run').mkdir(); (campaign/'run/manifest.json').write_text('{}')
    with pytest.raises(ValueError, match='executable source changed'):
        background.prepare_resume(campaign)
    assert not (campaign/'background.json').exists()
    assert not (campaign/'background-exit.json').exists()
    with pytest.raises(FileExistsError):
        background.freeze_source(campaign)

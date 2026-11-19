"""The enlarged allocation is checked through the public plan API, without calls."""
import importlib.util
import json
from pathlib import Path
import subprocess

from rsi_lab.agent_bench import plan_experiment
from rsi_lab.infra.records import read_record

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('scale_builder', ROOT/'scripts/natural_experiment_config.py')
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def test_enlarged_bash_plan_covers_all_roots_tasks_rounds_and_random_arm(tmp_path):
    script = ROOT/'scripts/run_scale_experiment.sh'
    settings = json.loads(script.read_text().split("<<'JSON'\n", 1)[1].split('\nJSON\n', 1)[0])
    config, money = builder.build(settings)
    assert config['task_pack'] == 'privacy-drafts-v3'
    assert config['arms'] == ['native_only', 'behavior_review', 'random_reject']
    assert config['random_reject']['probability'] == .5
    assert config['risk_report']['calibration']['confirmed'] is False
    assert config['slots'] == 5 and len(config['seeds']) == 8
    assert config['budget']['test_episodes'] == config['observations']['budget']['episodes'] == 24
    assert config['review']['budget']['episodes'] == 20
    assert money['budget_cny'] is None and money['within_budget'] is True
    assert config['execution']['max_total_calls'] == sum(a['max_calls'] for a in money['allocations'])
    campaign = tmp_path/'large-plan'
    result = subprocess.run(['bash', str(script), 'plan', str(campaign)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    plan = read_record(campaign/'plan.json')
    assert plan == plan_experiment(config)
    assert plan['root_count'] == 80 and plan['final_episodes_total'] == 1920
    assert plan['api_calls'] == 0 and not (campaign/'run').exists()
    assert len({case['task_id'].rsplit('_', 1)[0] for case in plan['evaluation_cases']}) == 6
    assert (campaign/'reports.json').is_file()
    assert (campaign/'launch.sh').read_bytes() == script.read_bytes()

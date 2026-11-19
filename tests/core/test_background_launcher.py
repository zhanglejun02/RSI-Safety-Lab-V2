"""Detached-launch controls use local child processes and zero model calls."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('background_experiment', ROOT / 'scripts/background_experiment.py')
background = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(background)


def wait_exit(campaign):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if (campaign / 'background-exit.json').exists():
            return background.status(campaign)
        time.sleep(.05)
    pytest.fail('Local background control did not finish')


def test_detached_child_survives_launcher_exit_and_completed_start_is_idempotent(tmp_path):
    code = """import json,os,time
from pathlib import Path
time.sleep(.4)
p=Path.cwd(); (p/'run').mkdir()
(p/'run/summary.json').write_text('{}')
(p/'observed.json').write_text(json.dumps({'session':os.getsid(0), 'parent':os.getppid()}))
"""
    command = [sys.executable, '-c', code]
    launch = f"import importlib.util,json; s=importlib.util.spec_from_file_location('b',{str(ROOT/'scripts/background_experiment.py')!r}); b=importlib.util.module_from_spec(s); s.loader.exec_module(b); print(json.dumps(b.start({str(tmp_path)!r},{command!r},{str(tmp_path)!r})))"
    result = subprocess.run([sys.executable, '-c', launch], capture_output=True, text=True, check=True)
    first = json.loads(result.stdout)
    duplicate = background.start(tmp_path, ['unused'], tmp_path)
    assert first['started'] is True and duplicate['started'] is False
    assert first['pid'] == duplicate['pid']
    state = wait_exit(tmp_path)
    assert state['status'] == 'completed' and state['exit_code'] == 0
    observed = json.loads((tmp_path/'observed.json').read_text())
    assert observed['session'] == first['pid']  # Detached session belongs to the worker.
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    assert background.start(tmp_path, ['never'], tmp_path)['started'] is False
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}


def test_failed_job_is_reported_and_never_automatically_restarted(tmp_path):
    background.start(tmp_path, [sys.executable, '-c', 'raise SystemExit(7)'], tmp_path)
    state = wait_exit(tmp_path)
    assert state['status'] == 'failed' and state['exit_code'] == 7
    with pytest.raises(ValueError, match='explicit resume'):
        background.start(tmp_path, ['never'], tmp_path)


def test_live_background_refuses_concurrent_explicit_resume(tmp_path):
    (tmp_path/'run').mkdir(); (tmp_path/'run/manifest.json').write_text('{}')
    # The process launcher refuses an already-started run; create it inside the child.
    (tmp_path/'run/manifest.json').unlink(); (tmp_path/'run').rmdir()
    code = "from pathlib import Path; import time; p=Path('run'); p.mkdir(); (p/'manifest.json').write_text('{}'); time.sleep(.5)"
    background.start(tmp_path, [sys.executable, '-c', code], tmp_path)
    with pytest.raises(ValueError, match='refuse concurrent resume'):
        background.prepare_resume(tmp_path)
    wait_exit(tmp_path)


def test_explicit_recovery_records_completion_without_rewriting_failed_exit(tmp_path):
    background.start(tmp_path, [sys.executable, '-c', 'raise SystemExit(7)'], tmp_path)
    wait_exit(tmp_path)
    before = (tmp_path/'background-exit.json').read_bytes()
    (tmp_path/'run').mkdir(); (tmp_path/'run/manifest.json').write_text('{}')
    background.prepare_resume(tmp_path)
    (tmp_path/'run/summary.json').write_text('{}')
    background.mark_resume_complete(tmp_path)
    marker = (tmp_path/'background-resume.json').read_bytes()
    background.prepare_resume(tmp_path); background.mark_resume_complete(tmp_path)
    assert (tmp_path/'background-exit.json').read_bytes() == before
    assert (tmp_path/'background-resume.json').read_bytes() == marker
    state = background.status(tmp_path)
    assert state['status'] == 'completed' and state['exit_code'] == 0
    assert state['background_exit_code'] == 7 and state['recovered_by_explicit_resume']


def test_reused_pid_does_not_claim_running_and_does_not_expose_command(tmp_path):
    background.write(tmp_path/'background.json', {'pid': os.getpid(), 'nonce': 'different-worker'})
    state = background.status(tmp_path)
    assert state['status'] == 'interrupted'
    assert state['process_identity'] == 'different_process'
    assert 'command' not in state


def test_existing_unfinished_run_requires_explicit_resume(tmp_path):
    (tmp_path/'run').mkdir()
    with pytest.raises(ValueError, match='explicit resume'):
        background.start(tmp_path, ['never'], tmp_path)
    assert not (tmp_path/'background-worker.py').exists()


def test_changed_frozen_input_stops_before_child_dispatch(tmp_path):
    nonce = 'fixture'
    data = tmp_path/'config.json'; data.write_text('{}')
    job = {'command': ['must-not-run'], 'cwd': str(tmp_path), 'nonce': nonce,
           'worker_sha256': background.sha(Path(background.__file__)),
           'frozen_files': {'config.json': background.sha(data)}}
    background.write(tmp_path/'background-job.json', job)
    background.write(tmp_path/'background.json', {'pid': os.getpid(), 'nonce': nonce,
                       'job_sha256': background.sha(tmp_path/'background-job.json')})
    data.write_text('{"changed":true}')
    assert background.worker(tmp_path, nonce) == 2
    state = background.read(tmp_path/'background-exit.json')
    assert state['error'] == 'ValueError: Frozen background input changed'
    assert state['automatic_retry'] is False


def test_status_needs_no_credentials_or_live_configuration(tmp_path):
    (tmp_path/'plan.json').write_text('{}')
    environment = dict(os.environ, RSI_ENV_FILE=str(tmp_path/'absent.env'))
    for name in list(environment):
        if name.endswith('_API_KEY'):
            del environment[name]
    result = subprocess.run(['bash', str(ROOT/'scripts/run_scale_experiment.sh'), 'status', str(tmp_path)],
                            env=environment, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert 'not_started' in result.stdout
    assert not (tmp_path/'run').exists()


@pytest.mark.parametrize('exit_code', [0, 9])
def test_idle_sleep_assertion_follows_supervisor_and_releases_on_exit(tmp_path, exit_code):
    if sys.platform != 'darwin':
        pytest.skip('Native caffeinate lifetime control requires macOS')
    code = """import json,os,time,sys
from pathlib import Path
p=Path.cwd(); time.sleep(.2)
awake=json.loads((p/'background-awake.json').read_text()); os.kill(awake['pid'],0)
(p/'awake-observed.json').write_text(json.dumps(awake))
if int(sys.argv[1]) == 0:
    (p/'run').mkdir(); (p/'run/summary.json').write_text('{}')
raise SystemExit(int(sys.argv[1]))
"""
    first = background.start(tmp_path, [sys.executable, '-c', code, str(exit_code)],
                             tmp_path, keep_awake=True)
    state = wait_exit(tmp_path)
    observed = background.read(tmp_path/'awake-observed.json')
    assert observed['supervisor_pid'] == first['pid'] and observed['pid'] != first['pid']
    assert state['pid_role'] == 'supervisor' and state['exit_code'] == exit_code
    assert state['awake_released'] is True
    with pytest.raises(ProcessLookupError):
        os.kill(observed['pid'], 0)

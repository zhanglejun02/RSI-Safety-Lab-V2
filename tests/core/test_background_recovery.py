"""Explicit detached recovery keeps old attempts and never reissues requests itself."""
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / 'scripts/background_experiment.py'
SPEC = importlib.util.spec_from_file_location('recovery_background', HELPER)
background = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(background)


def wait_for(campaign, filename):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if (campaign / filename).exists():
            return background.status(campaign)
        time.sleep(.05)
    pytest.fail('Local recovery control did not finish')


def original_failed_attempt(campaign, *, real_driver=None):
    q = shlex.quote
    # This frozen driver exercises the real resume guard, then a local stand-in
    # for the public CLI. No network or experiment credentials are involved.
    driver = campaign / 'background-driver.sh'
    driver.write_text(
        'set -euo pipefail\n'
        '[[ "$1" == resume ]]\n'
        + q(sys.executable) + ' ' + q(str(HELPER)) + ' prepare-resume "$2"\n'
        + q(sys.executable) + " - \"$2\" <<'PY'\n"
        'import json,os,sys,time,fixturepackage\nfrom pathlib import Path\n'
        'p=Path(sys.argv[1]); time.sleep(.4)\n'
        "(p/'observed.json').write_text(json.dumps({'session':os.getsid(0), 'package':fixturepackage.__file__}))\n"
        "if (p/'fail-control').exists(): raise SystemExit(7)\n"
        "(p/'run/summary.json').write_text('{}')\nPY\n")
    package = campaign / 'execution-source/package'
    package.mkdir(parents=True)
    (package / 'fixturepackage.py').write_text('VALUE=1\n')
    background.write(campaign / 'execution-source.json', {'files': {
        'package/fixturepackage.py': background.sha(package / 'fixturepackage.py')}})
    (campaign / 'background-run.sh').write_text(
        '#!/usr/bin/env bash\nset -euo pipefail\n'
        + 'export PYTHONPATH=' + q(str(package)) + '\n'
        + 'export PYTHONSAFEPATH=1\nexport PYTHONDONTWRITEBYTECODE=1\n'
        + 'source ' + q(str(driver)) + ' run ' + q(str(campaign)) + '\n')
    if real_driver is not None:
        driver.write_bytes(real_driver.read_bytes())
        repo_scripts = campaign / 'checkout/scripts'
        repo_scripts.mkdir(parents=True)
        (repo_scripts / 'background_experiment.py').write_bytes(HELPER.read_bytes())
        runner = campaign / 'background-run.sh'
        runner.write_text(runner.read_text().replace('set -euo pipefail\n',
            'set -euo pipefail\n'
            + 'export RSI_PYTHON=' + q(sys.executable) + '\n'
            + 'export RSI_ENV_FILE=' + q(str(campaign / 'absent.env')) + '\n'
            + 'LAUNCH_SCRIPT=' + q(str(repo_scripts / 'launcher.sh')) + '\n'))
        (campaign / 'config.json').write_text('{"task_pack":"local-control"}')
        (campaign / 'config-builder.py').write_text('import sys\nassert sys.argv[2] == "--check-budget"\n')
        (campaign / 'summarize.py').write_text('')
        cli = package / 'rsi_lab'
        cli.mkdir()
        (cli / '__init__.py').write_text('')
        (cli / 'cli.py').write_text(
            'import json,os,sys,time\nfrom pathlib import Path\n'
            "if sys.argv[1] == 'run':\n"
            "    assert '--resume' in sys.argv\n"
            "    p=Path(sys.argv[sys.argv.index('--output')+1]); time.sleep(.3)\n"
            "    (p/'summary.json').write_text('{}')\n"
            "    (p.parent/'actual-driver-observed.json').write_text(json.dumps({'file':__file__, 'args':sys.argv, 'session':os.getsid(0)}))\n")
        background.write(campaign / 'execution-source.json', {'files': {
            p.relative_to(campaign / 'execution-source').as_posix(): background.sha(p)
            for p in package.rglob('*') if p.is_file()}})
    (campaign / 'plan.json').write_text('{}')
    command = [sys.executable, '-c',
               "from pathlib import Path; p=Path('run'); p.mkdir(); (p/'manifest.json').write_text('{}'); raise SystemExit(9)"]
    background.start(campaign, command, campaign)
    wait_for(campaign, 'background-exit.json')
    return {p.name: p.read_bytes() for p in campaign.glob('background*') if p.is_file()}


def test_detached_recovery_uses_original_package_and_completed_resume_is_readonly(tmp_path):
    originals = original_failed_attempt(tmp_path)
    # A poison checkout cannot override the frozen package.
    (tmp_path / 'fixturepackage.py').write_text('raise RuntimeError("checkout changed")\n')
    launch = subprocess.run([sys.executable, str(HELPER), 'resume-start', str(tmp_path)],
                            capture_output=True, text=True, check=True)
    started = json.loads(launch.stdout)
    assert started['started'] and started['status'] == 'resuming'
    duplicate = background.resume_start(tmp_path)
    assert duplicate['pid'] == started['pid'] and not duplicate['started']
    assert duplicate['original_finished_at']
    assert 'original_awake_released' in duplicate
    assert 'finished_at' not in duplicate and 'awake_released' not in duplicate
    with pytest.raises(ValueError, match='refuse concurrent resume'):
        background.prepare_resume(tmp_path)
    attempt = background.recovery_directory(tmp_path, started['recovery_nonce'])
    state = wait_for(tmp_path, str((attempt / 'exit.json').relative_to(tmp_path)))
    assert state['status'] == 'completed' and state['exit_code'] == 0
    observed = background.read(tmp_path / 'observed.json')
    assert observed['session'] == started['pid']
    assert Path(observed['package']).is_relative_to(tmp_path / 'execution-source/package')
    assert originals == {name: (tmp_path / name).read_bytes() for name in originals}
    assert background.read(tmp_path / 'background-resume.json')['automatic_retry'] is False
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    assert not background.resume_start(tmp_path)['started']
    assert before == {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}


def test_failed_recovery_never_retries_and_next_explicit_attempt_is_separate(tmp_path):
    original_failed_attempt(tmp_path)
    (tmp_path / 'fail-control').touch()
    first = background.resume_start(tmp_path)
    first_dir = background.recovery_directory(tmp_path, first['recovery_nonce'])
    state = wait_for(tmp_path, str((first_dir / 'exit.json').relative_to(tmp_path)))
    assert state['status'] == 'failed' and state['exit_code'] == 7
    first_files = {p.name: p.read_bytes() for p in first_dir.iterdir() if p.is_file()}
    assert len(list((tmp_path / 'background-recoveries').iterdir())) == 1
    (tmp_path / 'fail-control').unlink()
    second = background.resume_start(tmp_path)
    assert second['recovery_nonce'] != first['recovery_nonce']
    second_dir = background.recovery_directory(tmp_path, second['recovery_nonce'])
    state = wait_for(tmp_path, str((second_dir / 'exit.json').relative_to(tmp_path)))
    assert state['status'] == 'completed'
    assert first_files == {p.name: p.read_bytes() for p in first_dir.iterdir() if p.is_file()}


def test_changed_executable_package_refuses_recovery_before_dispatch(tmp_path):
    original_failed_attempt(tmp_path)
    (tmp_path / 'execution-source/package/fixturepackage.py').write_text('VALUE=2\n')
    with pytest.raises(ValueError, match='executable source changed'):
        background.resume_start(tmp_path)
    assert not (tmp_path / 'background-recoveries').exists()


def test_bash_completed_recovery_needs_no_credentials_or_new_settings(tmp_path):
    (tmp_path / 'plan.json').write_text('{}')
    (tmp_path / 'run').mkdir()
    (tmp_path / 'run/summary.json').write_text('{}')
    environment = dict(os.environ, RSI_ENV_FILE=str(tmp_path / 'missing.env'))
    for name in list(environment):
        if name.endswith('_API_KEY'):
            del environment[name]
    result = subprocess.run(['bash', str(ROOT / 'scripts/run_scale_experiment.sh'),
                             'resume-start', str(tmp_path)], env=environment,
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert '"started": false' in result.stdout and '"status": "completed"' in result.stdout
    assert not (tmp_path / 'background-recoveries').exists()


def test_actual_shared_driver_recognizes_own_recovery_and_uses_frozen_pythonpath(tmp_path):
    # CI uses today's driver; release validation also points this at the exact
    # archived driver from the interrupted campaign, without changing that run.
    driver = Path(os.environ.get('RSI_FROZEN_DRIVER', ROOT / 'scripts/launch_natural_experiment.sh'))
    original_failed_attempt(tmp_path, real_driver=driver)
    result = background.resume_start(tmp_path)
    attempt = background.recovery_directory(tmp_path, result['recovery_nonce'])
    state = wait_for(tmp_path, str((attempt / 'exit.json').relative_to(tmp_path)))
    assert state['status'] == 'completed', (attempt / 'background.log').read_text()
    observed = background.read(tmp_path / 'actual-driver-observed.json')
    assert Path(observed['file']).is_relative_to(tmp_path / 'execution-source/package')
    assert observed['session'] == result['pid']
    assert '--resume' in observed['args']


def direct_failed_attempt(campaign, *, wrapped=False, defect=None):
    """Freeze the scoring launcher's actual shape around a zero-API fake CLI."""
    campaign.mkdir()
    package = campaign / 'execution-source/package/rsi_lab'
    package.mkdir(parents=True)
    (package / '__init__.py').write_text('')
    (package / 'cli.py').write_text(
        'import json,os,sys\nfrom pathlib import Path\n'
        'def main(args=None):\n'
        '    args=sys.argv[1:] if args is None else args\n'
        "    p=Path(args[args.index('--output')+1]).parent\n"
        "    expected=['run','--config',str(p/'config.json'),'--output',str(p/'run'),'--plan',str(p/'plan.json'),'--resume']\n"
        '    assert args == expected\n'
        "    (p/'observed.json').write_text(json.dumps({'args':args,'file':__file__,'session':os.getsid(0),'nonce':os.environ.get('RSI_BACKGROUND_RESUME_NONCE')}))\n"
        "    (p/'run/summary.json').write_text('{}')\n"
        "if __name__ == '__main__': main()\n")
    background.write(campaign / 'execution-source.json', {'files': {
        p.relative_to(campaign / 'execution-source').as_posix(): background.sha(p)
        for p in package.rglob('*') if p.is_file()}})
    (campaign / 'config.json').write_text('{}')
    (campaign / 'plan.json').write_text('{}')
    arguments = ['run', '--config', str(campaign / 'config.json'), '--output', str(campaign / 'run'),
                 '--plan', str(campaign / 'plan.json'), '--resume']
    if defect == 'no_resume':
        arguments.pop()
    elif defect in ('--config', '--output', '--plan'):
        arguments[arguments.index(defect) + 1] = str(campaign / 'wrong-path')
    if wrapped:
        wrapper = 'import sys\nfrom rsi_lab.cli import main\nraise SystemExit(main(sys.argv[3:]))'
        command = [sys.executable, '-c', wrapper, str(campaign / 'missing.env'),
                   str(campaign / 'run/summary.json'), *arguments]
    else:
        command = [sys.executable, '-m', 'rsi_lab.cli', *arguments]
    if defect == 'wrong_cli':
        command[2] = 'unrelated_command'
    header = '#!/usr/bin/env bash\nset -euo pipefail\n'
    driver = campaign / 'background-driver.sh'
    driver.write_text(header + 'export PYTHONDONTWRITEBYTECODE=1 PYTHONSAFEPATH=1\n'
                      + 'export PYTHONPATH=' + shlex.quote(str(package.parent)) + '\n'
                      + 'exec ' + shlex.join(command)
                      + ('; echo unexpected' if defect == 'shell_suffix' else '') + '\n')
    (campaign / 'background-run.sh').write_text(header + 'exec bash ' + shlex.quote(str(driver)) + '\n'
                                               + ('echo unexpected\n' if defect == 'runner_suffix' else ''))
    # The initial interruption is local. Only explicit recovery runs the driver.
    background.start(campaign, [sys.executable, '-c',
        "from pathlib import Path; p=Path('run'); p.mkdir(); (p/'manifest.json').write_text('{}'); raise SystemExit(9)"], campaign)
    wait_for(campaign, 'background-exit.json')
    return {p.relative_to(campaign): p.read_bytes() for p in campaign.rglob('*') if p.is_file()}


@pytest.mark.parametrize('wrapped', [False, True], ids=['module-cli', 'multiline-http-wrapper'])
def test_direct_scoring_driver_recovers_frozen_inputs_without_rewriting_originals(tmp_path, wrapped):
    campaign = tmp_path / 'scoring campaign with spaces'
    originals = direct_failed_attempt(campaign, wrapped=wrapped)
    # A later checkout must not supply the CLI even for the -c wrapper.
    checkout = campaign / 'rsi_lab'
    checkout.mkdir()
    (checkout / '__init__.py').write_text('raise RuntimeError("live checkout must not execute")\n')
    started = background.resume_start(campaign)
    attempt = background.recovery_directory(campaign, started['recovery_nonce'])
    state = wait_for(campaign, str((attempt / 'exit.json').relative_to(campaign)))
    assert state['status'] == 'completed', (attempt / 'background.log').read_text()
    observed = background.read(campaign / 'observed.json')
    assert observed['nonce'] == started['recovery_nonce']
    assert observed['session'] == started['pid']
    assert Path(observed['file']).is_relative_to(campaign / 'execution-source/package')
    assert observed['args'][-1] == '--resume'
    assert originals == {path: (campaign / path).read_bytes() for path in originals}
    before = {p.relative_to(campaign): p.read_bytes() for p in campaign.rglob('*') if p.is_file()}
    assert not background.resume_start(campaign)['started']
    assert before == {p.relative_to(campaign): p.read_bytes() for p in campaign.rglob('*') if p.is_file()}


@pytest.mark.parametrize('defect', ['no_resume', '--config', '--output', '--plan',
                                  'shell_suffix', 'runner_suffix', 'wrong_cli'])
def test_direct_runner_refuses_unrecognized_or_nonresume_commands_before_dispatch(tmp_path, defect):
    campaign = tmp_path / 'bad-scoring-runner'
    originals = direct_failed_attempt(campaign, defect=defect)
    with pytest.raises(ValueError, match='refuse recovery'):
        background.resume_start(campaign)
    assert not (campaign / 'background-recoveries').exists()
    assert not (campaign / 'observed.json').exists()
    assert originals == {path: (campaign / path).read_bytes() for path in originals}

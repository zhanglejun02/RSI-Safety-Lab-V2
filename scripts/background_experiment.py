"""Detached process support for the Bash launcher; never retries a run.

The experiment still executes through the public CLI and its frozen plan. This
helper owns only process identity, an append-only log and a terminal exit record.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
import time
import uuid


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2) + '\n')
    os.replace(temp, path)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze_source(campaign):
    """Archive trusted package/plugin sources using the existing run machinery."""
    from rsi_lab.agent_bench import plan_experiment
    from rsi_lab.infra.records import read_record, save_record
    from rsi_lab.review import _source, inventory
    from rsi_lab.studies.agent_bench import _archive

    config = read(campaign / 'config.json')
    plan = read_record(campaign / 'plan.json')
    if plan_experiment(config) != plan:
        raise ValueError('Frozen source or allocation changed; create a new campaign')
    target = campaign / 'execution-source'
    target.mkdir()  # Never replace the executable source of an existing attempt.
    save_record(target / 'manifest.json', {'implementation': plan['implementation'], 'roots': plan['roots']})
    _archive(target)
    for name, raw in _source(target).items():
        path = target / 'package' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as out:
            out.write(raw)
    # Also bind non-Python package data; the core fingerprint alone does not.
    write(campaign / 'execution-source.json', {
        'protocol': 'rsi-executable-source-v1', 'implementation': plan['implementation'],
        'files': inventory(target),
        'dependencies': 'Existing virtualenv/site packages and pinned external task assets; not vendored here'})


def verify_source(campaign):
    binding = campaign / 'execution-source.json'
    if not binding.exists():
        return  # Private process controls need no experiment package.
    source = campaign / 'execution-source'
    expected = read(binding)['files']
    actual = {}
    for path in source.rglob('*'):
        if path.is_symlink():
            raise ValueError('Executable source contains a symlink')
        if path.is_file():
            actual[path.relative_to(source).as_posix()] = sha(path)
    if actual != expected:
        raise ValueError('Frozen executable source changed')


def prepare_resume(campaign):
    """Explicit recovery may use frozen inputs, but never race a live worker."""
    current = status(campaign)
    own_recovery = (current.get('recovery_nonce') == os.environ.get('RSI_BACKGROUND_RESUME_NONCE')
                    and current.get('recovery_nonce') is not None
                    and current.get('process_identity') == 'matching'
                    and os.getpgrp() == current['pid'])
    if current['status'] in ('running', 'resuming', 'postprocessing', 'process_unknown') and not own_recovery:
        raise ValueError('Background job is active or its identity is unknown; refuse concurrent resume')
    if not (campaign / 'run/manifest.json').is_file():
        raise ValueError('No started run to resume')
    identity_path = campaign / 'background.json'
    if identity_path.exists():
        identity = read(identity_path)
        job_path = campaign / 'background-job.json'
        job = read(job_path)
        if identity['job_sha256'] != sha(job_path) or identity['nonce'] != job['nonce']:
            raise ValueError('Background recovery identity changed')
        for name, expected in job['frozen_files'].items():
            if Path(name).name != name or sha(campaign / name) != expected:
                raise ValueError('Frozen recovery input changed')
    verify_source(campaign)


def mark_resume_complete(campaign):
    """Keep the failed attempt's exit record; separately record explicit recovery."""
    exit_path = campaign / 'background-exit.json'
    if not (campaign / 'background.json').exists() or exit_path.exists() and read(exit_path)['exit_code'] == 0:
        return
    identity = read(campaign / 'background.json')
    marker = campaign / 'background-resume.json'
    summary_sha = sha(campaign / 'run/summary.json')
    if marker.exists():
        saved = read(marker)
        if saved['nonce'] != identity['nonce'] or saved['summary_sha256'] != summary_sha:
            raise ValueError('Completed recovery identity changed')
        return
    write(marker, {'nonce': identity['nonce'], 'summary_sha256': summary_sha,
                   'finished_at': now(), 'automatic_retry': False})


def process_state(campaign, record):
    """Never mistake a reused PID for the campaign worker or print its command."""
    try:
        os.kill(record['pid'], 0)
    except ProcessLookupError:
        return 'absent'
    except PermissionError:
        return 'unknown'
    try:
        result = subprocess.run(['ps', '-p', str(record['pid']), '-o', 'command='],
                                capture_output=True, text=True)
    except OSError:
        return 'unknown'
    if result.returncode:
        return 'unknown'
    worker_path = campaign / record.get('worker_path', 'background-worker.py')
    action = record.get('worker_action', 'worker')
    expected = f"{worker_path} {action} {campaign} {record['nonce']}"
    return 'matching' if result.stdout.strip().endswith(expected) else 'different_process'


def status(campaign):
    campaign = Path(campaign).resolve()
    state = campaign / 'background.json'
    record = read(state) if state.exists() else None
    exit_path = campaign / 'background-exit.json'
    result = {'campaign': str(campaign), 'status': 'not_started', 'pid': None, 'pid_role': 'supervisor',
              'process_identity': None, 'exit_code': None,
              'log': str(campaign / 'background.log')}
    complete = (campaign / 'run/summary.json').is_file()
    if record:
        result['pid'] = record['pid']
        result['keep_awake'] = record.get('keep_awake', False)
        if exit_path.exists():
            ended = read(exit_path)
            if ended['nonce'] != record['nonce']:
                raise ValueError('Background exit identity changed')
            result.update(exit_code=ended['exit_code'], finished_at=ended['finished_at'])
            result['awake_released'] = ended.get('awake_released')
            result['process_identity'] = 'finished'
            result['status'] = 'completed' if ended['exit_code'] == 0 and complete else 'failed'
        else:
            identity = process_state(campaign, record)
            result['process_identity'] = identity
            if identity == 'matching':
                result['status'] = 'postprocessing' if complete else 'running'
            else:
                result['status'] = 'interrupted' if identity in ('absent', 'different_process') else 'process_unknown'
        recovery = campaign / 'background-resume.json'
        if complete and recovery.exists():
            saved = read(recovery)
            if saved['nonce'] != record['nonce'] or saved['summary_sha256'] != sha(campaign / 'run/summary.json'):
                raise ValueError('Completed recovery identity changed')
            result.update(status='completed', recovered_by_explicit_resume=True,
                          background_exit_code=result['exit_code'], exit_code=0,
                          resume_finished_at=saved['finished_at'])
    elif complete:
        result['status'] = 'completed'
    elif (campaign / 'run').exists():
        result['status'] = 'existing_run'
    recovery_path = campaign / 'background-recovery.json'
    if recovery_path.exists():
        pointer = read(recovery_path)
        attempt = recovery_directory(campaign, pointer['nonce'])
        recovery = read(attempt / 'identity.json')
        if recovery['nonce'] != pointer['nonce']:
            raise ValueError('Recovery pointer identity changed')
        result.update(original_status=result['status'], original_exit_code=result['exit_code'],
                      pid=recovery['pid'], recovery_nonce=recovery['nonce'],
                      log=str(attempt / 'background.log'), keep_awake=recovery.get('keep_awake', False))
        # Terminal metadata belongs to the old attempt until this recovery exits.
        for key in ('finished_at', 'awake_released'):
            if key in result:
                result['original_' + key] = result.pop(key)
        if (attempt / 'exit.json').exists():
            ended = read(attempt / 'exit.json')
            if ended['nonce'] != recovery['nonce']:
                raise ValueError('Recovery exit identity changed')
            result.update(status='completed' if ended['exit_code'] == 0 and complete else 'failed',
                          exit_code=ended['exit_code'], finished_at=ended['finished_at'],
                          process_identity='finished', awake_released=ended.get('awake_released'))
        else:
            identity = process_state(campaign, recovery)
            result.update(process_identity=identity, exit_code=None)
            result['status'] = ('resuming' if identity == 'matching' else
                                'interrupted' if identity in ('absent', 'different_process') else 'process_unknown')
    result['summary_exists'] = complete
    result['progress'] = {key: len(list((campaign / 'run/roots').glob('*/' + filename)))
                          for key, filename in (('generated_roots', 'generation.json'),
                                                ('audited_roots', 'audit.json'),
                                                ('evaluated_roots', 'scores.json'))}
    return result


def start(campaign, command, cwd, *, keep_awake=False):
    campaign, cwd = Path(campaign).resolve(), Path(cwd).resolve()
    lock = campaign / '.background-start.lock'
    try:
        lock.mkdir()
    except FileExistsError:
        raise ValueError('Another start is in progress; no process was launched') from None
    try:
        current = status(campaign)
        if current['status'] in ('running', 'resuming', 'postprocessing', 'completed'):
            return current | {'started': False}
        if current['status'] != 'not_started' or (campaign / 'background-job.json').exists():
            raise ValueError('A previous attempt exists. Inspect it and use explicit resume; no automatic restart')
        worker = campaign / 'background-worker.py'
        shutil.copyfile(__file__, worker)
        job = campaign / 'background-job.json'
        nonce = uuid.uuid4().hex
        frozen_names = ('background-run.sh', 'background-driver.sh', 'config.json',
                        'plan.json', 'settings.json', 'budget.json', 'summarize.py',
                        'summarize_search.py', 'summarize_comparison.py', 'reports.json',
                        'config-builder.py', 'execution-source.json', 'readiness.json')
        verify_source(campaign)
        write(job, {'command': command, 'cwd': str(cwd), 'nonce': nonce,
                    'worker_sha256': sha(worker), 'automatic_retry': False,
                    'keep_awake': keep_awake,
                    'frozen_files': {name: sha(campaign / name) for name in frozen_names
                                     if (campaign / name).is_file()}})
        with (campaign / 'background.log').open('ab', buffering=0) as log:
            child = subprocess.Popen([sys.executable, str(worker), 'worker', str(campaign), nonce],
                                     cwd=cwd, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                     start_new_session=True, close_fds=True)
        write(campaign / 'background.json', {'protocol': 'rsi-background-process-v1',
              'pid': child.pid, 'nonce': nonce, 'started_at': now(), 'job_sha256': sha(job),
              'keep_awake': keep_awake})
        return {'campaign': str(campaign), 'status': 'starting', 'started': True,
                'pid': child.pid, 'log': str(campaign / 'background.log')}
    finally:
        lock.rmdir()


def recovery_directory(campaign, nonce):
    if len(nonce) != 32 or any(c not in '0123456789abcdef' for c in nonce):
        raise ValueError('Invalid recovery identity')
    return campaign / 'background-recoveries' / nonce


def resume_script(campaign, original_run, nonce):
    """Recognize frozen launchers without replaying a non-resumable command."""
    driver = campaign / 'background-driver.sh'
    export = 'export RSI_BACKGROUND_RESUME_NONCE=' + shlex.quote(nonce) + '\n'
    suffix = 'source ' + shlex.quote(str(driver)) + ' run ' + shlex.quote(str(campaign)) + '\n'
    if original_run.endswith(suffix):
        return (original_run[:-len(suffix)] + export
                + 'source ' + shlex.quote(str(driver)) + ' resume ' + shlex.quote(str(campaign)) + '\n')

    # The scoring launcher already embeds --resume in its immutable driver.
    # Accept only its exact runner and canonical argv, not arbitrary shell code
    # that happens to contain the expected paths or a --resume substring.
    header = '#!/usr/bin/env bash\nset -euo pipefail\n'
    command = 'exec bash ' + shlex.quote(str(driver)) + '\n'
    if original_run != header + command:
        raise ValueError('Unrecognized frozen background runner; refuse recovery')
    driver_header = (header + 'export PYTHONDONTWRITEBYTECODE=1 PYTHONSAFEPATH=1\n'
                     + 'export PYTHONPATH=' + shlex.quote(str(campaign / 'execution-source/package')) + '\n')
    saved_driver = driver.read_text()
    if not saved_driver.startswith(driver_header + 'exec '):
        raise ValueError('Unrecognized frozen resume driver; refuse recovery')
    execution = saved_driver[len(driver_header):]
    try:
        argv = shlex.split(execution[len('exec '):])
    except ValueError:
        raise ValueError('Unrecognized frozen resume command; refuse recovery') from None
    expected = ['run', '--config', str(campaign / 'config.json'), '--output', str(campaign / 'run'),
                '--plan', str(campaign / 'plan.json'), '--resume']
    prefix = argv[:-len(expected)]
    module_cli = len(prefix) == 3 and prefix[1:] == ['-m', 'rsi_lab.cli']
    wrapped_cli = (len(prefix) == 5 and prefix[1] == '-c'
                   and prefix[-1] == str(campaign / 'run/summary.json'))
    if (execution != 'exec ' + shlex.join(argv) + '\n' or argv[-len(expected):] != expected
            or not (module_cli or wrapped_cli)):
        raise ValueError('Frozen driver is not an explicit resume command; refuse recovery')
    return header + export + command


def resume_start(campaign):
    """Explicit detached recovery, retaining every prior attempt and frozen input."""
    campaign = Path(campaign).resolve()
    lock = campaign / '.background-start.lock'
    try:
        lock.mkdir()
    except FileExistsError:
        raise ValueError('Another start is in progress; no process was launched') from None
    try:
        current = status(campaign)
        if current['status'] in ('running', 'resuming', 'postprocessing', 'completed'):
            return current | {'started': False}
        prepare_resume(campaign)
        # Retain the original environment and driver; only select explicit resume.
        original_job = read(campaign / 'background-job.json')
        original_run = (campaign / 'background-run.sh').read_text()
        nonce = uuid.uuid4().hex
        recovery_script = resume_script(campaign, original_run, nonce)
        attempt = recovery_directory(campaign, nonce)
        attempt.mkdir(parents=True)
        worker_path = attempt / 'worker.py'
        shutil.copyfile(__file__, worker_path)
        script = attempt / 'run.sh'
        script.write_text(recovery_script)
        keep_awake = original_job.get('keep_awake', False)
        job_path = attempt / 'job.json'
        write(job_path, {'command': ['bash', str(script)], 'cwd': original_job['cwd'],
                        'nonce': nonce, 'worker_sha256': sha(worker_path),
                        'automatic_retry': False, 'keep_awake': keep_awake,
                        'frozen_files': original_job['frozen_files'],
                        'recovery_script_sha256': sha(script),
                        'original_job_sha256': sha(campaign / 'background-job.json')})
        with (attempt / 'background.log').open('ab', buffering=0) as log:
            child = subprocess.Popen([sys.executable, str(worker_path), 'recovery-worker', str(campaign), nonce],
                                     cwd=original_job['cwd'], stdin=subprocess.DEVNULL, stdout=log,
                                     stderr=subprocess.STDOUT, start_new_session=True, close_fds=True)
        write(attempt / 'identity.json', {'protocol': 'rsi-background-recovery-v1',
              'pid': child.pid, 'nonce': nonce, 'started_at': now(), 'job_sha256': sha(job_path),
              'keep_awake': keep_awake, 'worker_path': str(worker_path.relative_to(campaign)),
              'worker_action': 'recovery-worker'})
        write(campaign / 'background-recovery.json', {'nonce': nonce})
        return {'campaign': str(campaign), 'status': 'resuming', 'started': True,
                'pid': child.pid, 'recovery_nonce': nonce, 'log': str(attempt / 'background.log')}
    finally:
        lock.rmdir()


def worker(campaign, nonce, *, recovery=False):
    code, error = 2, None
    awake = None
    attempt = recovery_directory(campaign, nonce) if recovery else campaign
    identity_path = attempt / ('identity.json' if recovery else 'background.json')
    job_path = attempt / ('job.json' if recovery else 'background-job.json')
    try:
        # Do not dispatch unless the parent durably saved this exact process ID.
        for _ in range(50):
            if identity_path.exists() and (not recovery or
                    (campaign / 'background-recovery.json').exists() and
                    read(campaign / 'background-recovery.json')['nonce'] == nonce):
                break
            time.sleep(0.1)
        identity, job = read(identity_path), read(job_path)
        if (identity['pid'] != os.getpid() or identity['nonce'] != nonce or job['nonce'] != nonce
                or identity['job_sha256'] != sha(job_path)
                or job['worker_sha256'] != sha(Path(__file__))):
            raise ValueError('Background worker identity changed')
        for name, expected in job['frozen_files'].items():
            if Path(name).name != name or sha(campaign / name) != expected:
                raise ValueError('Frozen background input changed')
        verify_source(campaign)
        if recovery and (sha(attempt / 'run.sh') != job['recovery_script_sha256']
                         or sha(campaign / 'background-job.json') != job['original_job_sha256']
                         or read(campaign / 'background-recovery.json')['nonce'] != nonce):
            raise ValueError('Frozen recovery job changed')
        if job.get('keep_awake'):
            if sys.platform != 'darwin' or not Path('/usr/bin/caffeinate').is_file():
                raise ValueError('KEEP_AWAKE requires macOS caffeinate')
            # The assertion follows this supervisor's lifetime even if it is
            # killed. Explicit cleanup also releases it on normal/error exit.
            awake = subprocess.Popen(['/usr/bin/caffeinate', '-i', '-w', str(os.getpid())],
                                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
            write(attempt / 'background-awake.json', {'nonce': nonce, 'pid': awake.pid,
                                                       'supervisor_pid': os.getpid()})
        code = subprocess.run(job['command'], cwd=job['cwd'], stdin=subprocess.DEVNULL).returncode
        if recovery and code == 0:
            mark_resume_complete(campaign)
    except Exception as exc:
        code = 2
        error = type(exc).__name__ + ': ' + str(exc)
    finally:
        if awake is not None:
            if awake.poll() is None:
                awake.terminate()
            try:
                awake.wait(timeout=10)
            except subprocess.TimeoutExpired:
                awake.kill()
                awake.wait()
        write(attempt / ('exit.json' if recovery else 'background-exit.json'), {'nonce': nonce, 'exit_code': code,
              'finished_at': now(), 'error': error, 'automatic_retry': False,
              'awake_pid': awake.pid if awake is not None else None,
              'awake_released': awake.returncode is not None if awake is not None else None})
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('start', 'resume-start', 'status', 'worker', 'recovery-worker', 'freeze-source',
                                         'prepare-resume', 'resume-complete'))
    parser.add_argument('campaign', type=Path)
    parser.add_argument('arguments', nargs='*')
    args = parser.parse_args()
    campaign = args.campaign.resolve()
    if args.action == 'freeze-source':
        freeze_source(campaign)
        return 0
    if args.action == 'prepare-resume':
        prepare_resume(campaign)
        return 0
    if args.action == 'resume-complete':
        mark_resume_complete(campaign)
        return 0
    if args.action == 'worker':
        return worker(campaign, args.arguments[0])
    if args.action == 'recovery-worker':
        return worker(campaign, args.arguments[0], recovery=True)
    if args.action == 'status':
        result = status(campaign)
    elif args.action == 'resume-start':
        result = resume_start(campaign)
    else:
        option = args.arguments[1] if len(args.arguments) > 1 else 'false'
        if option not in ('true', 'false'):
            raise ValueError('KEEP_AWAKE must be true or false')
        result = start(campaign, ['bash', str(campaign / 'background-run.sh')], args.arguments[0],
                       keep_awake=option == 'true')
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError) as exc:
        print('BackgroundError: ' + str(exc), file=sys.stderr)
        raise SystemExit(2) from None

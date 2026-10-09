"""One-shot Linux CI harness: original Relay, separate OS browser users, no TLS bypass.

Only public CA bytes cross into the browser user's home. Runtime, service logs and
credentials stay owned by the runner. No browser operation runs as the PC owner.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import socket
import stat
import subprocess
import sys
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'storage/runtime'
OUT = RUNTIME / 'browser-sync-qa/network-ci'
PUBLIC_BROWSER = Path('/opt/rh-qa-browser')
APP = ROOT / 'apps/browser-qa'


def safe_diagnostics(raw):
    """Classification only; never return fragments of untrusted/private logs."""
    patterns = {'ACCESS_DENIED': (b'EACCES', b'Permission denied'),
                'OPERATION_NOT_PERMITTED': (b'EPERM', b'Operation not permitted'),
                'MISSING_BROWSER': (b"Executable doesn't exist",),
                'MISSING_MODULE': (b'MODULE_NOT_FOUND',),
                'SANDBOX_UNAVAILABLE': (b'No usable sandbox',),
                'MISSING_SHARED_LIBRARY': (b'error while loading shared libraries',)}
    return [code for code, needles in patterns.items() if any(n in raw for n in needles)]


class StageFailure(RuntimeError):
    def __init__(self, stage):
        self.stage = stage
        super().__init__('QA_STAGE_FAILED')


def safe_crashpad_probe(raw):
    """Only fixed path-selection metadata; never publish selected path or env."""
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError('INVALID_CRASHPAD_PROBE')
    allowed = {
        'selector': {'CHROME_CONFIG_HOME', 'XDG_CONFIG_HOME', 'HOME_FALLBACK'},
        'lexicalLocation': {'INSIDE_HOME', 'OUTSIDE_HOME', 'UNKNOWN'},
        'realLocation': {'INSIDE_HOME', 'OUTSIDE_HOME', 'UNKNOWN'},
        'targetState': {'EXISTS', 'MISSING', 'INACCESSIBLE'},
        'nearestType': {'DIRECTORY', 'FILE', 'OTHER', 'UNKNOWN'},
        'ancestorAccess': {'WRITABLE_SEARCHABLE', 'DENIED', 'UNKNOWN'},
        'createProbe': {'NOT_ATTEMPTED', 'CREATED', 'CREATED_AND_REMOVED', 'CREATE_FAILED', 'CLEANUP_FAILED'},
        'probeError': {None, 'EACCES', 'EPERM', 'ENOENT', 'ENOTDIR', 'EROFS', 'ENOSPC', 'UNKNOWN'},
    }
    result = {'probeKind': 'NODE_FS_PRELAUNCH_CFT_PATH'}
    for field, choices in allowed.items():
        candidate = value.get(field)
        result[field] = candidate if (candidate is None or isinstance(candidate, str)) and candidate in choices else 'UNKNOWN'
    for field in ('absolute', 'homeMatchesAccount'):
        result[field] = value.get(field) if type(value.get(field)) is bool else None
    return result


def browser_env_command(args, values=None):
    """Reset only inherited directory overrides for the QA child process."""
    values = values or {}
    if not set(values) <= {'RH_B2_RESULTS', 'RH_B2_BUILD_HASH', 'RH_B2_TLS_CASE',
                          'PLAYWRIGHT_BROWSERS_PATH', 'GITHUB_SHA',
                          'RH_IMPORT_PHASE', 'RH_IMPORT_MODULE', 'RH_IMPORT_SOURCE_DIR',
                          'RH_FAILURE_CASE', 'RH_FAILURE_CONTROL'}:
        raise ValueError('UNEXPECTED_QA_ENV_KEY')
    removed = ('CHROME_CONFIG_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME',
               'XDG_DATA_HOME', 'XDG_STATE_HOME')
    return ['env', *(arg for name in removed for arg in ('-u', name)),
            *(f'{key}={value}' for key, value in values.items()), *args]


def clean_probe_ready(probe):
    expected = {'selector': 'HOME_FALLBACK', 'absolute': True, 'homeMatchesAccount': True,
                'lexicalLocation': 'INSIDE_HOME', 'realLocation': 'INSIDE_HOME',
                'nearestType': 'DIRECTORY', 'ancestorAccess': 'WRITABLE_SEARCHABLE',
                'createProbe': 'CREATED_AND_REMOVED', 'probeError': None}
    return all(type(probe.get(key)) is type(value) and probe.get(key) == value
               for key, value in expected.items())


def owned_process_metadata(uid):
    """Fixed fields for this run's newly created UID; never collect argv/env."""
    result = subprocess.run(['ps', '-u', str(uid), '-o', 'pid=,ppid=,stat=,comm='],
                            capture_output=True, text=True, check=False)
    rows = []
    allowed = {'systemd', '(sd-pam)', 'dbus-daemon', 'chrome', 'chromium',
               'chrome_crashpad', 'node', 'bash', 'sh', 'sudo', 'certutil'}
    for line in result.stdout.splitlines():
        fields = line.split(maxsplit=3)
        if len(fields) != 4 or not fields[0].isdigit() or not fields[1].isdigit():
            continue
        rows.append({'pid': int(fields[0]), 'parentPid': int(fields[1]),
                     'state': fields[2][0] if fields[2][0] in 'RSDTtZXIPW' else 'UNKNOWN',
                     'kind': fields[3] if fields[3] in allowed else 'OTHER'})
    return {'uid': uid, 'exitCode': result.returncode, 'processes': rows}


def only_login_session(rows):
    managers = {row['pid'] for row in rows if row['kind'] == 'systemd'
                and row['parentPid'] == 1 and row['state'] in ('S', 'R')}
    return bool(managers) and all(
        row['pid'] in managers or (row['kind'] == '(sd-pam)'
                                  and row['parentPid'] in managers and row['state'] in ('S', 'R'))
        for row in rows)


def process_cleanup_failures(snapshot, probe_exit):
    failures = []
    if probe_exit not in (0, 1) or snapshot['exitCode'] not in (0, 1):
        failures.append('ProcessProbeFailed')
    # A leak observed by either probe cannot be erased by a later process exit.
    if (snapshot['processes'] or probe_exit == 0) and not only_login_session(snapshot['processes']):
        failures.append('OwnedProcessesRemain')
    return failures


def network_scenario(scenario):
    choices = {
        'baseline': {'directory': 'network-ci', 'config': 'playwright.network.config.ts',
                     'node': 'ci-browser-pairing'},
        'conflict': {'directory': 'conflict-ci', 'config': 'playwright.conflict.config.ts',
                     'node': 'ci-browser-conflict'},
    }
    for module in ('hdsp', 'ice-sonocuring'):
        choices['import-' + module] = {
            'directory': 'import-' + module + '-ci', 'config': 'playwright.import.config.ts',
            'node': 'ci-browser-import-' + module, 'module': module}
    for case in ('reopen','pc-offline','independent-echo','ack-loss','revoked-write','historical-bootstrap','privacy'):
        choices['failure-' + case] = {'directory': 'failure-' + case + '-ci',
            'config': 'playwright.failure.config.ts', 'node': 'ci-failure-' + case, 'failure': case}
    if not isinstance(scenario, str) or scenario not in choices:
        raise ValueError('UNKNOWN_NETWORK_SCENARIO')
    return choices[scenario]


def main(scenario='baseline'):
    selected = network_scenario(scenario)
    importing = 'module' in selected
    failure_case = selected.get('failure')
    OUT = RUNTIME / 'browser-sync-qa' / selected['directory']
    if sys.platform != 'linux' or os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('EPHEMERAL_LINUX_CI_ONLY')
    if os.environ.get('HUB_SYNC_QA') != '1' or os.environ.get('HUB_RELAY_QA') != '1':
        raise RuntimeError('EXPLICIT_QA_REQUIRED')
    import pwd
    os.umask(0o077)
    RUNTIME.mkdir(parents=True, exist_ok=True)
    RUNTIME.chmod(0o700)
    git_metadata = ROOT / '.git'
    if git_metadata.is_dir():
        git_metadata.chmod(0o700)
    OUT.mkdir(parents=True, exist_ok=False)
    evidence = {'scope': 'SYNTHETIC isolated Linux browser network',
                'sourceCommit': os.environ['GITHUB_SHA'], 'TLS_001': 'OPEN',
                'PRODUCTION_READY': False, 'scenario': scenario, 'stages': [], 'status': 'RUNNING'}
    services = []
    logs = []
    owned_user_ids = []
    relay_attempted = False
    current_stage = 'initialize'
    controller = None
    failure_actions = None

    def save():
        (OUT / 'harness-summary.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')

    def run(stage, args, *, env=None, cwd=ROOT, timeout=300, control=None):
        nonlocal current_stage
        current_stage = stage
        path = OUT / (stage + '.private.log')
        with path.open('xb') as log:
            try:
                if control is None:
                    result = subprocess.run(args, cwd=cwd, env=env, stdout=log,
                                            stderr=subprocess.STDOUT, timeout=timeout, check=False)
                    code = result.returncode
                else:
                    from browser_failure_control import run_controlled
                    code = run_controlled(args, cwd=cwd, env=env, log=log, timeout=timeout, controller=control)
                current_stage = stage
            except subprocess.TimeoutExpired:
                code = 'TIMEOUT'
            except OSError:
                code = 'SPAWN_ERROR'
                if control is not None:
                    import traceback
                    log.write(traceback.format_exc().encode('utf-8'))
                    code = 'CONTROL_OS_ERROR'
            except Exception:
                if control is None:
                    raise
                import traceback
                log.write(traceback.format_exc().encode('utf-8'))
                code = 'CONTROL_ERROR'
        raw_log = path.read_bytes()
        evidence['stages'].append({'stage': stage, 'exitCode': code,
                                  'privateLogSha256': hashlib.sha256(raw_log).hexdigest(),
                                  'diagnostics': safe_diagnostics(raw_log)})
        save()
        if code != 0:
            raise StageFailure(stage)

    def as_user(user, args, *, values=None, cwd=APP, clean_browser=False):
        # sudo login selects the account's actual home; never overwrite HOME.
        child = browser_env_command(args, values) if clean_browser else ['env', *(f'{k}={v}' for k, v in (values or {}).items()), *args]
        command = shlex.join(child)
        return ['sudo', '--login', '--user', user, '--', 'sh', '-c',
                'cd ' + shlex.quote(str(cwd)) + ' && exec ' + command]

    def start_service(name, args, origin, env, *, instance=''):
        nonlocal current_stage
        current_stage = name + instance + '-start'
        port = int(origin.rsplit(':', 1)[1])
        owner_path = RUNTIME / ('browser-sync-qa/pc/server-owner.json' if name == 'pc'
                                else 'browser-local-qa/server-owner.json' if name == 'source-static'
                                else 'browser-sync-qa/server-owner.json')
        if owner_path.exists():
            raise RuntimeError('EXISTING_QA_OWNER_REQUIRED_REVIEW')
        with socket.socket() as probe:
            if probe.connect_ex(('127.0.0.1', port)) == 0:
                raise RuntimeError('OCCUPIED_QA_PORT')
        log_path = OUT / (name + instance + '.private.log')
        log = log_path.open('xb')
        logs.append(log)
        try:
            process = subprocess.Popen(args, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        except OSError:
            log.flush()
            evidence['stages'].append({'stage': current_stage, 'exitCode': 'SPAWN_ERROR',
                'privateLogSha256': hashlib.sha256(Path(log.name).read_bytes()).hexdigest()})
            save()
            raise StageFailure(current_stage) from None
        services.append((name, process, log_path))
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError('OWNED_SERVICE_EXITED')
            try:
                with urlopen(origin, timeout=1) as response:
                    if response.status == 200:
                        evidence['stages'].append({'stage': current_stage, 'exitCode': 0})
                        save()
                        return
            except OSError:
                time.sleep(0.1)  # Startup readiness only, never test/business retries.
        raise RuntimeError('OWNED_SERVICE_START_TIMEOUT')

    try:
        if (RUNTIME / 'secure-relay-run.json').exists():
            raise RuntimeError('FRESH_CI_RELAY_REQUIRED')
        node = shutil.which('node')
        if not node or not PUBLIC_BROWSER.is_dir():
            raise RuntimeError('PUBLIC_NODE_BROWSER_REQUIRED')
        users = {}
        browser_users = [('trusted', 'rhqatlsgood')] if importing or failure_case else [('untrusted', 'rhqatlsbad'), ('trusted', 'rhqatlsgood')]
        for case, user in browser_users:
            run('user-' + case, ['sudo', 'useradd', '--create-home', '--shell', '/bin/bash', user])
            account = pwd.getpwnam(user)
            owned_user_ids.append(account.pw_uid)
            home = Path(account.pw_dir)
            if home != Path('/home') / user:
                raise RuntimeError('UNEXPECTED_QA_USER_HOME')
            users[case] = (user, home)
            # A private runner home may need traverse-only access. Do not expose
            # its directory listing, change ownership, or grant runtime access.
            for index, parent in enumerate(ROOT.parents):
                if not parent.stat().st_mode & stat.S_IXOTH:
                    run('traverse-' + case + '-' + str(index), ['sudo', 'setfacl', '-m',
                        'u:' + user + ':--x', str(parent)])
            nss = home / '.local/share/pki/nssdb'
            run('nss-dir-' + case, as_user(user, ['mkdir', '-p', str(nss)], cwd=home))
            run('nss-new-' + case, as_user(user, ['certutil', '-N', '-d', 'sql:' + str(nss),
                                              '--empty-password'], cwd=home))
            evidence.setdefault('userProcessBaselines', []).append(owned_process_metadata(account.pw_uid))
            save()
        relay_attempted = True
        run('relay-init', [sys.executable, 'scripts/secure-relay-qa.py', '--init'], timeout=600)
        state = json.loads((RUNTIME / 'secure-relay-run.json').read_text())
        tls_dir = Path(state['tls_directory']).resolve()
        if not tls_dir.is_relative_to(RUNTIME.resolve()) or state.get('phase') != 'ready':
            raise RuntimeError('RELAY_READY_CA_REQUIRED')
        public_ca = tls_dir / 'ca.crt'
        user, home = users['trusted']
        # install only the public certificate, not state, TLS directory or private keys.
        run('copy-public-ca', ['sudo', 'install', '-m', '0644', '-o', user, '-g', user,
                              str(public_ca), str(home / 'qa-ca.crt')])
        run('trust-public-ca', as_user(user, ['certutil', '-A', '-d', 'sql:' + str(home / '.local/share/pki/nssdb'),
                                           '-t', 'C,,', '-n', 'ResearchHub-isolated-QA',
                                           '-i', str(home / 'qa-ca.crt')], cwd=home))
        evidence['caSha256'] = hashlib.sha256(public_ca.read_bytes()).hexdigest()
        env = {**os.environ, 'PYTHONPATH': str(ROOT / 'apps/api') + os.pathsep + str(ROOT)}
        if not importing:
            run('pc-setup', [sys.executable, '-m', 'researchhub.sync.pc_cli', 'setup', '--node', selected['node']], env=env)
            start_service('pc', [sys.executable, '-m', 'researchhub.sync.pc_cli', 'start', '--node', selected['node']],
                          'http://127.0.0.1:3315', env)
        else:
            start_service('source-static', [node, 'apps/browser-qa/scripts/server.mjs'],
                          'http://127.0.0.1:3313', {**env, 'RH_QA_PROFILE': 'local'})
        start_service('browser-static', [node, 'apps/browser-qa/scripts/server.mjs'],
                      'http://127.0.0.1:3314', {**env, 'RH_QA_PROFILE': 'sync'})
        build = RUNTIME / 'browser-sync-qa/dist'
        build_hash = hashlib.sha256((build / 'app.js').read_bytes() + (build / 'app.css').read_bytes()).hexdigest()
        pc_build = RUNTIME / 'browser-sync-qa/pc/dist'
        evidence['buildHashes'] = {'browser': build_hash, 'pc': hashlib.sha256(
            (pc_build / 'app.js').read_bytes() + (pc_build / 'app.css').read_bytes()).hexdigest()}
        if importing:
            source_build = RUNTIME / 'browser-local-qa/dist'
            evidence['buildHashes']['source3A'] = hashlib.sha256(
                (source_build / 'app.js').read_bytes() + (source_build / 'app.css').read_bytes()).hexdigest()
        cases = [('prepare', users['trusted']), ('trusted', users['trusted'])] if importing else list(users.items())
        for case, (user, home) in cases:
            results = home / ('source-results' if case == 'prepare' else 'network-results')
            values = {'RH_B2_RESULTS': str(results), 'RH_B2_BUILD_HASH': build_hash,
                      'RH_B2_TLS_CASE': 'trusted' if importing else case, 'PLAYWRIGHT_BROWSERS_PATH': str(PUBLIC_BROWSER),
                      'GITHUB_SHA': os.environ['GITHUB_SHA']}
            if failure_case:
                import tempfile
                from browser_failure_control import Controller, RealActions
                directory = Path(tempfile.mkdtemp(prefix='rh-failure-'))
                directory.chmod(0o1733)
                def stop_matrix_pc():
                    owned = [p for name, p, _ in services if name == 'pc' and p.poll() is None]
                    owner = json.loads((RUNTIME / 'browser-sync-qa/pc/server-owner.json').read_text())
                    if len(owned) != 1 or owner.get('pid') != owned[0].pid:
                        raise RuntimeError('MATRIX_PC_OWNER_MISMATCH')
                    run('matrix-pc-stop', [sys.executable, '-m', 'researchhub.sync.pc_cli', 'stop'], env=env)
                    owned[0].wait(timeout=15)
                    if owned[0].returncode != 0:
                        raise RuntimeError('MATRIX_PC_STOP_FAILED')
                def start_matrix_pc():
                    if any(p.poll() is None for name, p, _ in services if name == 'pc'):
                        raise RuntimeError('MATRIX_PC_STILL_RUNNING')
                    start_service('pc', [sys.executable, '-m', 'researchhub.sync.pc_cli', 'start', '--node', selected['node']],
                        'http://127.0.0.1:3315', env, instance='-restarted')
                failure_actions = RealActions(ROOT, RUNTIME / 'browser-sync-qa/pc/nodes' / selected['node'],
                    stop_matrix_pc, start_matrix_pc, evidence.setdefault('failureMatrix', {}))
                controller = Controller(failure_case, directory, pwd.getpwnam(user).pw_uid, failure_actions, evidence['failureMatrix'])
                values.update({'RH_FAILURE_CASE': failure_case, 'RH_FAILURE_CONTROL': str(directory)})
            if importing:
                values.update({'RH_IMPORT_PHASE': 'prepare' if case == 'prepare' else 'apply',
                               'RH_IMPORT_MODULE': selected['module'],
                               'RH_IMPORT_SOURCE_DIR': str(home / 'import-source')})
            run('actual-home-' + case, as_user(user, [node, '-e',
                'const os=require("os");if(process.env.HOME!==os.userInfo().homedir)process.exit(2)'], cwd=home))
            # Observe the same login environment/cwd as Playwright, before any
            # browser launch. Do not override config variables or create its
            # default Crash Reports directory. The probe only creates/removes a
            # unique empty temporary directory when the real parent is in home.
            probe_stage = 'crashpad-path-' + case
            run(probe_stage, as_user(user, [node, 'scripts/crashpad-path-probe.mjs'], values=values))
            evidence.setdefault('crashpadPathProbes', {})[case] = safe_crashpad_probe(
                (OUT / (probe_stage + '.private.log')).read_text(encoding='utf-8'))
            save()
            if evidence['crashpadPathProbes'][case]['createProbe'] == 'CLEANUP_FAILED':
                raise StageFailure(probe_stage)
            # RH036 observed inherited XDG_CONFIG_HOME outside the new user's
            # home and EACCES. Keep that prior observation above, then verify
            # exactly the sanitized environment used by the browser below.
            clean_stage = 'crashpad-clean-path-' + case
            run(clean_stage, as_user(user, [node, 'scripts/crashpad-path-probe.mjs'],
                                    values=values, clean_browser=True))
            clean_probe = safe_crashpad_probe(
                (OUT / (clean_stage + '.private.log')).read_text(encoding='utf-8'))
            evidence.setdefault('crashpadCleanPathProbes', {})[case] = clean_probe
            save()
            if not clean_probe_ready(clean_probe):
                raise StageFailure(clean_stage)
            # Verify user separation by actual access denial before running browser tests.
            run('runtime-denied-' + case, as_user(user, [node, '-e',
                'const fs=require("fs");try{fs.readdirSync(process.argv[1]);process.exit(1)}'
                'catch(e){if(e.code!=="EACCES")throw e}', str(RUNTIME)], cwd=home))
            try:
                run('browser-' + case, as_user(user, [node, 'node_modules/@playwright/test/cli.js',
                    'test', '--config', selected['config']], values=values, clean_browser=True), timeout=420, control=controller)
            finally:
                # Only reviewed public summary is copied. Raw logs/profiles never leave home/runtime.
                summary = results / 'summary.json'
                present = subprocess.run(['sudo', 'test', '-f', str(summary)], check=False).returncode
                if present == 0:
                    run('collect-' + case, ['sudo', 'install', '-m', '0600', '-o', str(os.getuid()),
                        '-g', str(os.getgid()), str(summary), str(OUT / (case + '-summary.json'))])
                elif present != 1:
                    raise StageFailure('collect-' + case)
                if case == 'trusted' and present == 0:
                    public_result = json.loads((OUT / (case + '-summary.json')).read_text())
                    if public_result.get('status') == 'passed' and not failure_case:
                        screenshots = ('desktop.png', 'mobile.png')
                        if scenario == 'conflict':
                            screenshots += ('conflict-comparison.png', 'conflict-candidate.png')
                        if importing:
                            screenshots = ('import-desktop.png', 'import-mobile.png')
                        for filename in screenshots:
                            run('collect-' + filename.split('.')[0], ['sudo', 'install', '-m', '0600',
                                '-o', str(os.getuid()), '-g', str(os.getgid()), str(results / filename),
                                str(OUT / ('trusted-' + filename))])
            if importing and case == 'prepare':
                # Read as the browser UID with size/owner/no-symlink checks.
                # Only the validated descriptor crosses to the PC owner; the
                # rescue package and profiles remain in the browser's home.
                run('source-descriptor', as_user(user, [sys.executable,
                    str(ROOT / 'scripts/qa-source-descriptor.py'),
                    str(home / 'import-source/source-project.json')], cwd=home))
                descriptor = OUT / 'source-descriptor.private.log'
                source_args = ['--node', selected['node'], '--source-project', str(descriptor)]
                run('pc-setup', [sys.executable, '-m', 'researchhub.sync.pc_cli', 'setup', *source_args], env=env)
                start_service('pc', [sys.executable, '-m', 'researchhub.sync.pc_cli', 'start', *source_args],
                              'http://127.0.0.1:3315', env)
        evidence['status'] = 'PASS'
    except Exception as exc:
        evidence['status'] = 'FAIL'
        failed_stage = getattr(exc, 'stage', current_stage)
        evidence['failure'] = {'stage': failed_stage, 'errorClass': type(exc).__name__,
                               'exitCode': 'NOT_COMPLETED'}
        # Do not print exception text: remote/browser data can contain credentials or proofs.
        print('BROWSER_QA_FAILED stage=' + failed_stage + ' class=' + type(exc).__name__)
    finally:
        if failure_actions is not None:
            try:
                failure_actions.close()
            except Exception as exc:
                evidence['status'] = 'FAIL'
                evidence.setdefault('cleanupFailures', []).append({'service': 'matrix-database', 'errorClass': type(exc).__name__})
        for name, process, log_path in reversed(services):
            try:
                if process.poll() is None:
                    if name == 'pc':
                        run('pc-stop', [sys.executable, '-m', 'researchhub.sync.pc_cli', 'stop'], env=env)
                    else:
                        run(name + '-stop', [node, 'apps/browser-qa/scripts/stop.mjs'],
                            env={**env, 'RH_QA_PROFILE': 'local' if name == 'source-static' else 'sync'})
                    process.wait(timeout=15)
            except Exception as exc:
                evidence['status'] = 'FAIL'
                evidence.setdefault('cleanupFailures', []).append({'service': name, 'errorClass': type(exc).__name__})
                if process.poll() is None:
                    process.terminate()  # Only the exact child this harness created.
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
        for log in logs:
            log.close()
        evidence['ownedServiceResults'] = [
            {'service': name, 'exitCode': process.poll() if process.poll() is not None else 'STILL_RUNNING',
             'privateLogSha256': hashlib.sha256(log_path.read_bytes()).hexdigest()}
            for name, process, log_path in services]
        # A timed-out sudo child can leave Chromium descendants. These UIDs were
        # created by this run and cannot contain the user's personal processes.
        for uid in owned_user_ids:
            snapshot = owned_process_metadata(uid)
            evidence.setdefault('userProcessCleanupSnapshots', []).append(snapshot)
            remaining = subprocess.run(['pgrep', '-u', str(uid)], stdout=subprocess.DEVNULL, check=False)
            failures = process_cleanup_failures(snapshot, remaining.returncode)
            if failures:
                evidence['status'] = 'FAIL'
                evidence.setdefault('cleanupFailures', []).extend(
                    {'service': 'browser-user', 'errorClass': failure} for failure in failures)
            if remaining.returncode == 0:
                # sudo login created these account sessions before any browser ran.
                # Any additional process remains a failure, even if termination succeeds.
                try:
                    run('terminate-owned-user-' + str(uid), ['sudo', 'loginctl', 'terminate-user', str(uid)], timeout=15)
                    deadline = time.monotonic() + 5
                    while True:
                        check = subprocess.run(['pgrep', '-u', str(uid)], stdout=subprocess.DEVNULL, check=False)
                        if check.returncode == 1:
                            break
                        if check.returncode != 0 or time.monotonic() >= deadline:
                            raise StageFailure('owned-user-termination')
                        time.sleep(0.1)  # Owned session shutdown readiness, never a test retry.
                except Exception as exc:
                    evidence['status'] = 'FAIL'
                    evidence.setdefault('cleanupFailures', []).append({'service': 'browser-user', 'errorClass': type(exc).__name__})
                    subprocess.run(['sudo', 'pkill', '-TERM', '-u', str(uid)], check=False)
            final_snapshot = owned_process_metadata(uid)
            evidence.setdefault('userProcessAfterTermination', []).append(final_snapshot)
            if final_snapshot['exitCode'] != 1 or final_snapshot['processes']:
                evidence['status'] = 'FAIL'
                evidence.setdefault('cleanupFailures', []).append({'service': 'browser-user', 'errorClass': 'TerminationNotConfirmed'})
        if relay_attempted:
            try:
                run('relay-diagnostics', [sys.executable, 'scripts/secure-relay-diagnostics.py'])
            except Exception as exc:
                evidence['status'] = 'FAIL'
                evidence.setdefault('cleanupFailures', []).append({'service': 'diagnostics', 'errorClass': type(exc).__name__})
            try:
                run('relay-destroy', [sys.executable, 'scripts/secure-relay-qa.py', '--destroy'], timeout=300)
            except Exception as exc:
                evidence['status'] = 'FAIL'
                evidence.setdefault('cleanupFailures', []).append({'service': 'relay', 'errorClass': type(exc).__name__})
        save()
    print('BROWSER_QA_' + evidence['status'])
    return 0 if evidence['status'] == 'PASS' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', choices=('baseline', 'conflict', 'import-hdsp', 'import-ice-sonocuring'), default='baseline')
    sys.exit(main(parser.parse_args().scenario))

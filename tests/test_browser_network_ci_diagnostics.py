"""Allowlisted process evidence must not expose arbitrary names or arguments."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    'browser_network_ci', Path(__file__).resolve().parents[1] / 'scripts/browser-network-qa-ci.py')
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)


def test_owned_process_metadata_restricts_fields():
    result = SimpleNamespace(returncode=0, stdout='12 1 Ss systemd\n13 12 S (sd-pam)\n'
                             '14 1 Z secret-credential\nmalformed\n')
    with patch.object(harness.subprocess, 'run', return_value=result) as run:
        evidence = harness.owned_process_metadata(1002)
    assert evidence == {'uid': 1002, 'exitCode': 0, 'processes': [
        {'pid': 12, 'parentPid': 1, 'state': 'S', 'kind': 'systemd'},
        {'pid': 13, 'parentPid': 12, 'state': 'S', 'kind': '(sd-pam)'},
        {'pid': 14, 'parentPid': 1, 'state': 'Z', 'kind': 'OTHER'}]}
    assert run.call_args.args[0] == ['ps', '-u', '1002', '-o', 'pid=,ppid=,stat=,comm=']


def test_process_probe_failure_is_preserved():
    with patch.object(harness.subprocess, 'run', return_value=SimpleNamespace(returncode=1, stdout='')):
        assert harness.owned_process_metadata(1002) == {'uid': 1002, 'exitCode': 1, 'processes': []}


def test_only_owned_login_session_processes_are_recognized():
    session = [{'pid': 12, 'parentPid': 1, 'state': 'S', 'kind': 'systemd'},
               {'pid': 13, 'parentPid': 12, 'state': 'S', 'kind': '(sd-pam)'}]
    assert harness.only_login_session(session)
    assert not harness.only_login_session(session + [
        {'pid': 14, 'parentPid': 12, 'state': 'S', 'kind': 'chrome'}])
    assert not harness.only_login_session([
        {'pid': 13, 'parentPid': 999, 'state': 'S', 'kind': '(sd-pam)'}])
    assert not harness.only_login_session([
        {'pid': 12, 'parentPid': 3, 'state': 'S', 'kind': 'systemd'}])
    assert not harness.only_login_session([
        {'pid': 12, 'parentPid': 1, 'state': 'Z', 'kind': 'systemd'}])


def test_observed_browser_leak_remains_failure_if_it_exits_before_pgrep():
    snapshot = {'exitCode': 0, 'processes': [
        {'pid': 14, 'parentPid': 1, 'state': 'S', 'kind': 'chrome'}]}
    assert harness.process_cleanup_failures(snapshot, 1) == ['OwnedProcessesRemain']
    assert harness.process_cleanup_failures({'exitCode': 1, 'processes': []}, 1) == []
    assert harness.process_cleanup_failures({'exitCode': 1, 'processes': []}, 0) == ['OwnedProcessesRemain']

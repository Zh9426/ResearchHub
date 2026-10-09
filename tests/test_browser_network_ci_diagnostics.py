"""Allowlisted process evidence must not expose arbitrary names or arguments."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    'browser_network_ci', Path(__file__).resolve().parents[1] / 'scripts/browser-network-qa-ci.py')
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)


def test_network_scenarios_keep_baseline_and_conflict_isolated():
    assert harness.network_scenario('baseline') == {
        'directory': 'network-ci', 'config': 'playwright.network.config.ts',
        'node': 'ci-browser-pairing'}
    assert harness.network_scenario('conflict') == {
        'directory': 'conflict-ci', 'config': 'playwright.conflict.config.ts',
        'node': 'ci-browser-conflict'}
    import pytest
    for invalid in ('../private', '', 'production', None):
        with pytest.raises(ValueError, match='UNKNOWN_NETWORK_SCENARIO'):
            harness.network_scenario(invalid)


def test_import_scenarios_are_fixed_and_cannot_select_arbitrary_config():
    for module in ('hdsp', 'ice-sonocuring'):
        assert harness.network_scenario('import-' + module) == {
            'directory': 'import-' + module + '-ci', 'config': 'playwright.import.config.ts',
            'node': 'ci-browser-import-' + module, 'module': module}
    import pytest
    with pytest.raises(ValueError, match='UNKNOWN_NETWORK_SCENARIO'):
        harness.network_scenario('import-../../private')
    values = {'RH_IMPORT_PHASE': 'prepare', 'RH_IMPORT_MODULE': 'hdsp',
              'RH_IMPORT_SOURCE_DIR': '/home/synthetic/source'}
    assert harness.browser_env_command(['node'], values)[-4:] == [
        'RH_IMPORT_PHASE=prepare', 'RH_IMPORT_MODULE=hdsp',
        'RH_IMPORT_SOURCE_DIR=/home/synthetic/source', 'node']


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

def test_crashpad_probe_summary_rejects_untrusted_fields_and_values():
    assert hasattr(harness, 'safe_crashpad_probe')
    value={'selector':'CHROME_CONFIG_HOME','absolute':False,'homeMatchesAccount':True,
           'lexicalLocation':'OUTSIDE_HOME','realLocation':'OUTSIDE_HOME',
           'targetState':'MISSING','nearestType':'DIRECTORY','ancestorAccess':'WRITABLE_SEARCHABLE',
           'createProbe':'NOT_ATTEMPTED','probeError':None,'PRIVATE_SECRET':'do not expose'}
    import json
    report=harness.safe_crashpad_probe(json.dumps(value))
    assert report['selector']=='CHROME_CONFIG_HOME'
    assert 'PRIVATE_SECRET' not in json.dumps(report)
    value.update(selector='PRIVATE_PATH',probeError='PRIVATE_ERROR',absolute='PRIVATE')
    report=harness.safe_crashpad_probe(json.dumps(value))
    assert report['selector']=='UNKNOWN' and report['probeError']=='UNKNOWN'
    assert report['absolute'] is None

def test_browser_command_unsets_only_fixed_directory_overrides_and_never_home():
    assert hasattr(harness, 'browser_env_command')
    import os
    before=dict(os.environ)
    args=['node','probe.mjs']
    values={'RH_B2_TLS_CASE':'untrusted'}
    command=harness.browser_env_command(args,values)
    assert command==['env','-u','CHROME_CONFIG_HOME','-u','XDG_CONFIG_HOME',
                     '-u','XDG_CACHE_HOME','-u','XDG_DATA_HOME','-u','XDG_STATE_HOME',
                     'RH_B2_TLS_CASE=untrusted','node','probe.mjs']
    assert 'HOME' not in command and 'CODEX_HOME' not in command
    assert dict(os.environ)==before and args==['node','probe.mjs'] and values=={'RH_B2_TLS_CASE':'untrusted'}
    import pytest
    with pytest.raises(ValueError,match='UNEXPECTED_QA_ENV_KEY'):
        harness.browser_env_command(args,{'PRIVATE_BUSINESS_TOKEN':'SECRET'})


def test_post_sanitize_probe_gate_requires_actual_home_and_successful_cleanup():
    assert hasattr(harness, 'clean_probe_ready')
    good={'selector':'HOME_FALLBACK','absolute':True,'homeMatchesAccount':True,
          'lexicalLocation':'INSIDE_HOME','realLocation':'INSIDE_HOME',
          'nearestType':'DIRECTORY','ancestorAccess':'WRITABLE_SEARCHABLE',
          'createProbe':'CREATED_AND_REMOVED','probeError':None}
    assert harness.clean_probe_ready(good)
    for key,value in [('selector','XDG_CONFIG_HOME'),('homeMatchesAccount',False),
                      ('realLocation','OUTSIDE_HOME'),('ancestorAccess','DENIED'),
                      ('createProbe','CLEANUP_FAILED'),('probeError','EACCES')]:
        assert not harness.clean_probe_ready({**good,key:value})

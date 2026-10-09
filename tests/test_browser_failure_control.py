"""Fixed-step control protocol and filesystem boundary regressions."""
import importlib.util
import json
import os
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'scripts/browser_failure_control.py'

def load():
    assert SOURCE.is_file(), 'Fixed failure controller is not implemented'
    spec = importlib.util.spec_from_file_location('failure_control', SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def test_strict_fixed_fsm():
    m = load()
    for case, actions in m.CASE_ACTIONS.items():
        state = m.Protocol(case)
        for step, action in enumerate(actions, 1):
            value = dict(version=1, case=case, step=step, action=action)
            assert state.accept(json.dumps(value).encode()) == action
        assert state.finished
        with pytest.raises(ValueError, match='CONTROL_PROTOCOL_REJECTED'):
            state.accept(json.dumps(value).encode())

@pytest.mark.parametrize('patch', [
    {'step': 2}, {'step': True}, {'version': True}, {'case': 'ack-loss'},
    {'action': 'RELAY_START'}, {'command': 'anything'}, {'path': '/private'},
    {'pid': 1}, {'sql': 'SELECT 1'}, {'secret': 'redacted'},
])
def test_invalid_request_never_advances(patch):
    m = load(); state = m.Protocol('pc-offline')
    value = dict(version=1,case='pc-offline',step=1,action='PC_STOP')
    with pytest.raises(ValueError, match='CONTROL_PROTOCOL_REJECTED'):
        state.accept(json.dumps({**value, **patch}).encode())
    assert state.step == 0
    assert state.accept(json.dumps(value).encode()) == 'PC_STOP'

@pytest.mark.parametrize('raw', [b'[]', b'null', b'{', b' ' * 1025,
    b'{"version":1,"version":1,"case":"pc-offline","step":1,"action":"PC_STOP"}'],
    ids=['array','null','malformed','oversize','duplicate-key'])
def test_untrusted_json(raw):
    m = load()
    with pytest.raises(ValueError, match='CONTROL_PROTOCOL_REJECTED'):
        m.Protocol('pc-offline').accept(raw)

def test_no_arbitrary_case():
    m = load()
    for case in ('../private', None, [], 'production'):
        with pytest.raises(ValueError, match='CONTROL_PROTOCOL_REJECTED'):
            m.Protocol(case)

def test_regular_file_boundary(tmp_path):
    m = load(); path = tmp_path / 'command.json'; path.write_bytes(b'{}')
    uid = path.stat().st_uid
    assert m.read_owned_file(path, uid) == b'{}'
    with pytest.raises(ValueError, match='CONTROL_FILE_REJECTED'):
        m.read_owned_file(path, uid + 1)
    path.write_bytes(b'x' * 1025)
    with pytest.raises(ValueError, match='CONTROL_FILE_REJECTED'):
        m.read_owned_file(path, uid)
    with pytest.raises(ValueError, match='CONTROL_FILE_REJECTED'):
        m.read_owned_file(tmp_path, uid)

def test_hardlinked_control_file_is_rejected(tmp_path):
    m = load(); path = tmp_path / 'command.json'; alias = tmp_path / 'alias.json'
    path.write_bytes(b'{}'); os.link(path, alias)
    with pytest.raises(ValueError, match='CONTROL_FILE_REJECTED'):
        m.read_owned_file(path, path.stat().st_uid)

def test_link_metadata_rejected_before_open(tmp_path, monkeypatch):
    import stat
    from types import SimpleNamespace
    m = load(); path = tmp_path / 'command.json'; path.write_bytes(b'{}')
    fake = SimpleNamespace(st_mode=stat.S_IFLNK, st_uid=1234, st_nlink=1, st_size=2)
    monkeypatch.setattr(Path, 'lstat', lambda self: fake)
    def forbidden(*args):raise AssertionError('must not open a symlink')
    monkeypatch.setattr(m.os, 'open', forbidden)
    with pytest.raises(ValueError, match='CONTROL_FILE_REJECTED'):
        m.read_owned_file(path, 1234)

def test_inode_replacement_rejected(tmp_path, monkeypatch):
    from types import SimpleNamespace
    m = load(); path=tmp_path/'command.json';path.write_bytes(b'{}');info=path.stat()
    fake=SimpleNamespace(st_mode=info.st_mode,st_uid=info.st_uid,st_nlink=1,st_size=2,st_dev=info.st_dev,st_ino=info.st_ino+1)
    monkeypatch.setattr(m.os,'fstat',lambda fd:fake)
    with pytest.raises(ValueError,match='CONTROL_FILE_REJECTED'):
        m.read_owned_file(path, info.st_uid)

def test_valid_action_failure_is_never_advanced_into_success(tmp_path, monkeypatch):
    import stat
    from types import SimpleNamespace
    m=load();directory=tmp_path/'channel';directory.mkdir();uid=directory.stat().st_uid
    monkeypatch.setattr(m.os,'getuid',lambda:uid,raising=False)
    info=directory.stat();fake=SimpleNamespace(st_mode=stat.S_IFDIR|0o1733,st_uid=uid,st_dev=info.st_dev,st_ino=info.st_ino)
    original_stat=Path.stat;original_lstat=Path.lstat
    monkeypatch.setattr(Path,'stat',lambda self,*a,**k:fake if self==directory else original_stat(self,*a,**k))
    monkeypatch.setattr(Path,'lstat',lambda self,*a,**k:fake if self==directory else original_lstat(self,*a,**k))
    class Actions:
        def perform(self,action):raise RuntimeError('synthetic action failure')
    evidence={};controller=m.Controller('pc-offline',directory,uid,Actions(),evidence)
    (directory/'001.request.json').write_text(json.dumps(dict(version=1,case='pc-offline',step=1,action='PC_STOP')))
    responses=[];monkeypatch.setattr(controller,'respond',lambda step,status:responses.append((step,status)))
    with pytest.raises(RuntimeError,match='synthetic action failure'):controller.poll()
    assert responses==[(1,'FAILED')]
    assert evidence['control']==[dict(step=1,action='PC_STOP',status='FAILED')]
    assert not controller.protocol.finished

def test_control_keeps_action_and_response_failures(monkeypatch):
    from types import SimpleNamespace
    m=load();controller=object.__new__(m.Controller)
    controller.directory=Path('synthetic-channel');controller.directory_identity=SimpleNamespace(st_dev=1,st_ino=2)
    controller.browser_uid=1002;controller.protocol=m.Protocol('pc-offline');controller.evidence={}
    monkeypatch.setattr(m.os,'getuid',lambda:1001,raising=False)
    import stat
    monkeypatch.setattr(Path,'lstat',lambda self:SimpleNamespace(st_mode=stat.S_IFDIR|0o1733,st_uid=1001,st_dev=1,st_ino=2))
    monkeypatch.setattr(m,'read_owned_file',lambda *a:b'{"version":1,"case":"pc-offline","step":1,"action":"PC_STOP"}')
    def failed_action(action):raise RuntimeError('ACTION_FAILED')
    def failed_response(*args):raise OSError('RESPONSE_FAILED')
    controller.actions=SimpleNamespace(perform=failed_action);controller.respond=failed_response
    with pytest.raises(ExceptionGroup) as captured:controller.poll()
    assert [str(e) for e in captured.value.exceptions]==['ACTION_FAILED','RESPONSE_FAILED']

def test_controlled_runner_keeps_primary_and_cleanup_failures(monkeypatch):
    import subprocess
    from types import SimpleNamespace
    m=load()
    class Child:
        def poll(self):return None
        def terminate(self):raise OSError('TERMINATE_FAILED')
    monkeypatch.setattr(subprocess,'Popen',lambda *a,**k:Child())
    def fail():raise ValueError('CONTROL_ACTION_FAILED')
    with pytest.raises(ExceptionGroup) as captured:
        m.run_controlled(['synthetic'],cwd=ROOT,env={},log=None,timeout=1,controller=SimpleNamespace(poll=fail))
    assert [str(e) for e in captured.value.exceptions]==['CONTROL_ACTION_FAILED','TERMINATE_FAILED']

def test_fixed_matrix_scenarios_and_windows_refusal(monkeypatch):
    spec=importlib.util.spec_from_file_location('matrix_harness',ROOT/'scripts/browser-network-qa-ci.py')
    h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
    for case in load().CASE_ACTIONS:
        assert h.network_scenario('failure-'+case)=={'directory':'failure-'+case+'-ci','config':'playwright.failure.config.ts','node':'ci-failure-'+case,'failure':case}
    for case in ('failure-../secret','failure-', 'failure-shell'):
        with pytest.raises(ValueError,match='UNKNOWN_NETWORK_SCENARIO'):h.network_scenario(case)
    monkeypatch.setattr(h.sys,'platform','win32')
    with pytest.raises(RuntimeError,match='EPHEMERAL_LINUX_CI_ONLY'):h.main('failure-reopen')

def test_control_errors_do_not_expose_untrusted_messages():
    m=load()
    assert m.public_control_error(RuntimeError('DURABLE_EXPECTED_COUNTS_MISMATCH'))=={'errorClass':'RuntimeError','code':'DURABLE_EXPECTED_COUNTS_MISMATCH'}
    assert m.public_control_error(RuntimeError('PRIVATE_PROOF key=secret'))=={'errorClass':'RuntimeError','code':'UNCLASSIFIED'}

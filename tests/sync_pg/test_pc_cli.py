"""Owned lifecycle regression. Only subprocesses started here may be terminated."""
import os
import subprocess
import sys
import time
from pathlib import Path
import pytest
from researchhub.sync.pc_cli import node_path

@pytest.mark.parametrize('name',['../outside','..','C:\\Users\\Other','/tmp/other','CON','nul','com1','lpt9','name.txt','a/b','a\\b',''])
def test_invalid_node_name_refused(name):
    with pytest.raises(ValueError):node_path(Path('storage/runtime/browser-sync-qa/pc').resolve(),name)

def test_owned_start_stop_finishes():
    env={**os.environ,'HUB_SYNC_QA':'1','PYTHONPATH':os.pathsep.join(['apps/api','.'])}
    start=time.monotonic()
    server=subprocess.Popen([sys.executable,'-m','researchhub.sync.pc_cli','start'],env=env,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:
        assert 'PC_QA_READY' in server.stdout.readline()
        print('STAGE ready',round(time.monotonic()-start,3),server.pid)
        stopped=subprocess.run([sys.executable,'-m','researchhub.sync.pc_cli','stop'],env=env,
            capture_output=True,text=True,timeout=10,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        print('STAGE stop_returned',round(time.monotonic()-start,3),stopped.returncode)
        assert stopped.returncode==0,stopped.stderr
        server.wait(timeout=10)
        print('STAGE server_exited',round(time.monotonic()-start,3),server.returncode)
        assert server.returncode==0
        assert not Path('storage/runtime/browser-sync-qa/pc/server-owner.json').exists()
    finally:
        if server.poll() is None:server.terminate();server.wait(timeout=5)
        print('STAGE stderr',server.stderr.read())


def test_cli_has_explicit_setup_action(monkeypatch):
    import researchhub.sync.pc_cli as cli
    called=[]
    monkeypatch.setattr(sys,'argv',['pc_cli','setup','--node','synthetic-test'])
    monkeypatch.setattr(cli,'setup_selected_node',lambda path,module:called.append((path,module)),raising=False)
    cli.main()
    assert len(called)==1
    assert called[0][0].name=='synthetic-test'

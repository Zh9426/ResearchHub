"""Owned PC QA process only. Never terminate a PID found by port lookup."""
import argparse
import json
import os
import secrets
import socket
import re
from urllib.request import Request, urlopen
import uvicorn
from .pc_qa import ROOT,ORIGIN,create_app

def node_path(runtime,name):
    if name is None:return runtime/'node'
    if (not re.fullmatch(r'[a-z][a-z0-9-]{0,47}',name)
            or re.fullmatch(r'(con|prn|aux|nul|com[0-9]|lpt[0-9])',name,re.I)):
        raise ValueError('INVALID_QA_NODE_NAME')
    result=(runtime/'nodes'/name).resolve()
    if not result.is_relative_to((runtime/'nodes').resolve()):raise ValueError('INVALID_QA_NODE_PATH')
    return result


def setup_selected_node(path,module):
    from .secure.transport_pg import client_engine
    from .pc_identity import setup_node
    from .pc_pairing import pin_node_bootstrap,make_transport
    engine=client_engine()
    try:
        node=setup_node(engine,path,module)
        pin_node_bootstrap(node)
        transport=make_transport(engine,node)
        try:
            hello=transport.request('POST','/v1/hello',{})
            if hello['sequence']!=0 or hello['manifest_digest']!=node.binding['trust']['manifest_head']:
                raise ValueError('EMPTY_RELAY_PIN_REQUIRED')
        finally:transport.close()
        print('PC_QA_BOOTSTRAP_PINNED_EMPTY')
    finally:engine.dispose()

def main():
    parser=argparse.ArgumentParser(description='SYNTHETIC QA ONLY PC node at 127.0.0.1:3315')
    parser.add_argument('action',choices=('start','stop','setup'))
    parser.add_argument('--module',choices=('generic','hdsp','ice-sonocuring'),default='generic')
    parser.add_argument('--node',help='Optional isolated synthetic node slug, within owned PC runtime only')
    args=parser.parse_args()
    runtime=ROOT/'storage/runtime/browser-sync-qa/pc'
    selected_node=node_path(runtime,args.node)
    if args.action=='setup':
        setup_selected_node(selected_node,args.module);return
    owner_file=runtime/'server-owner.json'
    if args.action=='stop':
        owner=json.loads(owner_file.read_text())
        if owner.get('origin')!=ORIGIN:raise RuntimeError('Refusing unowned origin')
        req=Request(ORIGIN+'/_qa_stop',data=b'{}',method='POST',headers={
            'Origin':ORIGIN,'Content-Type':'application/json','X-QA-Owner':owner['token']})
        with urlopen(req,timeout=5) as response:
            if response.status!=200:raise RuntimeError('Refusing unowned service')
        print('Owned PC QA stopping');return
    if os.environ.get('HUB_SYNC_QA')!='1':raise RuntimeError('Explicit HUB_SYNC_QA=1 required')
    if owner_file.exists():raise RuntimeError('Existing owner file; verify owned process before recovery')
    # Bind first: an occupied port fails without setup or process termination.
    sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    if hasattr(socket,'SO_EXCLUSIVEADDRUSE'):sock.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
    sock.bind(('127.0.0.1',3315));sock.listen(128)
    token=secrets.token_urlsafe(32);runtime.mkdir(parents=True,exist_ok=True)
    try:
        with owner_file.open('x') as f:json.dump({'pid':os.getpid(),'token':token,'origin':ORIGIN},f)
        app=create_app(module_id=args.module,runtime=selected_node)
        app.state.stop_token=token
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=3315,access_log=False,log_level='info'))
        @app.post('/_qa_stop')
        def stop():
            print('PC_QA_STAGE stop_requested',flush=True)
            server.should_exit=True
            return {'status':'stopping'}
        print('PC_QA_READY '+ORIGIN,flush=True)
        server.run(sockets=[sock])
        print('PC_QA_STAGE server_run_returned',flush=True)
    finally:
        sock.close()
        if owner_file.exists() and json.loads(owner_file.read_text()).get('token')==token:owner_file.unlink()

if __name__=='__main__':main()

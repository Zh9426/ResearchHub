"""3315-only SYNTHETIC PC app factory. Does not import product main/settings."""
import os
import re
import secrets
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import ObjectRevision, Outbox
from .pc_identity import setup_node,current_binding
from .pc_records import RecordWork, execute_command, read_record
from .pc_transport import record_status
from .projection import project_status
from .protocol import ProtocolError
from .secure.transport_pg import client_engine, guard

ORIGIN='http://127.0.0.1:3315'
ROOT=Path(__file__).resolve().parents[4]

def local_object(kind,oid,pid,document,version):
    common={'id':oid,'project_id':pid,'kind':'Run' if kind=='ResearchRun' else 'Note',
        'title':document.get('title',''),'local_format_version':1,'local_edit_version':version}
    if kind=='Note':return {**common,'body':document.get('content','')}
    return {**common,'run_type':document.get('run_type','simulation'),
        **{k:document.get(k,'') for k in ('objective','observation','highlight_type','highlight_note')},
        'status':document.get('status','planned'),'scientific_outcome':document.get('scientific_outcome','unknown'),
        'context_data':document.get('context_data',{}),'is_highlighted':document.get('is_highlighted',False)}

def create_app(*,engine=None,runtime=None,module_id='generic',pairing_transport=None,source_project=None):
    if os.environ.get('HUB_SYNC_QA')!='1':raise RuntimeError('Explicit HUB_SYNC_QA=1 required')
    engine=engine or client_engine();guard(engine)
    node=setup_node(engine,runtime or ROOT/'storage/runtime/browser-sync-qa/pc/node',module_id,pairing_transport=pairing_transport,source_project=source_project)
    app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
    app.state.node=node
    sessions={}

    @app.middleware('http')
    async def boundary(request:Request,call_next):
        if request.headers.get('host')!='127.0.0.1:3315' or not request.client or request.client.host!='127.0.0.1':
            return JSONResponse({'error':'LOOPBACK_HOST_REQUIRED'},403)
        if request.headers.get('origin') not in (None,ORIGIN) or request.headers.get('sec-fetch-site')=='cross-site':
            return JSONResponse({'error':'ORIGIN_DENIED'},403)
        if request.method not in ('GET','POST'):
            return JSONResponse({'error':'METHOD_DENIED'},405)
        session=request.cookies.get('rh_pc_qa_session'); csrf=sessions.get(session)
        if request.url.path.startswith('/api/') and request.url.path!='/api/session' and csrf is None:
            return JSONResponse({'error':'SESSION_REQUIRED'},401)
        if request.method=='POST':
            owned_stop=(request.url.path=='/_qa_stop' and getattr(app.state,'stop_token',None)
                and secrets.compare_digest(request.headers.get('x-qa-owner',''),app.state.stop_token))
            if request.headers.get('origin')!=ORIGIN or (not owned_stop and (not csrf or not secrets.compare_digest(request.headers.get('x-pc-csrf',''),csrf))):
                return JSONResponse({'error':'CSRF_REQUIRED'},403)
            if request.headers.get('content-type','').split(';')[0].strip()!='application/json':
                return JSONResponse({'error':'JSON_REQUIRED'},415)
            body=await request.body()
            if len(body)>1024*1024:return JSONResponse({'error':'COMMAND_TOO_LARGE'},413)
        response=await call_next(request)
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['Content-Security-Policy']="default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response

    @app.exception_handler(ProtocolError)
    async def protocol_error(request,exc):
        return JSONResponse({'error':exc.code,'detail':str(exc)},409)

    @app.get('/api/session')
    def session(request:Request):
        sid=request.cookies.get('rh_pc_qa_session')
        if sid not in sessions:
            sid=secrets.token_urlsafe(32);sessions[sid]=secrets.token_urlsafe(32)
        result=JSONResponse({'csrf':sessions[sid]})
        result.set_cookie('rh_pc_qa_session',sid,httponly=True,samesite='strict',path='/')
        return result

    @app.get('/api/binding')
    def binding():
        binding,wrapper=current_binding(engine,node)
        return {'binding':binding,'signed_binding':wrapper,'pairing':'OWNER_TEXT_V1'}

    @app.get('/api/pairing/status')
    def pairing_status(session_id:str|None=None):
        from .pc_pairing import OwnerPairing
        owner=OwnerPairing(engine,node,None)
        try:return owner.status(session_id)
        except ValueError:return JSONResponse({'error':'PAIRING_SESSION_INVALID'},409)

    def pairing_operation(action,data):
        from .pc_pairing import OwnerPairing,make_transport
        import httpx
        transport=None
        try:
            try:
                transport=pairing_transport or make_transport(engine,node)
                owner=OwnerPairing(engine,node,transport)
            except ValueError as exc:
                if str(exc)=='RELAY_QA_SETUP_REQUIRED':
                    return JSONResponse({'error':'RELAY_UNAVAILABLE_RESUME_REQUIRED'},503)
                if str(exc)=='QA_CA_PATH_REQUIRED':
                    return JSONResponse({'error':'PAIRING_REJECTED_CHECK_STATUS'},409)
                raise
            try:
                if action=='start':return owner.start(data['recipient'])
                if action=='confirm':return owner.confirm(data['session_id'],data['proof'])
                return owner.resume(data['session_id'])
            except (ValueError,TypeError,KeyError):return JSONResponse({'error':'PAIRING_REJECTED_CHECK_STATUS'},409)
        except (httpx.HTTPError,OSError):return JSONResponse({'error':'RELAY_UNAVAILABLE_RESUME_REQUIRED'},503)
        finally:
            if pairing_transport is None and transport is not None:transport.close()

    @app.post('/api/pairing/{action}')
    async def pairing_action(action:str,request:Request):
        from packages.secure_wire.canonical import strict_loads
        from .secure.transport_bounds import bounded_canonical
        try:
            raw=await request.body();data=strict_loads(raw)
            if bounded_canonical(data)!=raw or type(data) is not dict:raise ValueError()
            fields={'start':{'recipient'},'confirm':{'session_id','proof'},'resume':{'session_id'}}
            if action not in fields or set(data)!=fields[action]:raise ValueError()
        except (ValueError,TypeError):return JSONResponse({'error':'CANONICAL_PAIRING_REQUEST_REQUIRED'},422)
        # Construction, PG/SQLite/network work and owned transport cleanup all block.
        return await run_in_threadpool(pairing_operation,action,data)

    @app.post('/api/sync')
    async def sync_now(request:Request):
        from packages.secure_wire.canonical import strict_loads
        try:
            if strict_loads(await request.body())!={}:raise ValueError()
        except ValueError:return JSONResponse({'error':'INVALID_SYNC_REQUEST'},422)
        def operation():
            import httpx
            from .pc_transport import PcTransport
            from .pc_pairing import make_transport
            from .secure.transport_pg import locked
            transport=None;primary=None
            try:
                try:
                    with Session(engine) as db,db.begin():
                        _,history=locked(db,node.binding['opaque_project_id'])
                        peers=[m for m in history[-1]['members'] if m['status']=='ACTIVE' and m['device_id']!=node.owner.device_id]
                        if len(peers)!=1:raise ValueError('EXACT_PEER_TARGET_REQUIRED')
                    transport=make_transport(engine,node)
                    return PcTransport(engine,node).cycle(transport)
                except Exception as exc:
                    primary=exc;raise
                finally:
                    if transport:
                        try:transport.close()
                        except Exception as cleanup:
                            if primary:raise ExceptionGroup('SYNC_AND_TRANSPORT_CLOSE_FAILED',[primary,cleanup]) from None
                            raise
            except ValueError as exc:
                code=str(exc) if re.fullmatch('[A-Z_]+',str(exc)) else 'SYNC_BLOCKED'
                return JSONResponse({'error':code},409)
            except (httpx.HTTPError,OSError):return JSONResponse({'error':'SYNC_NETWORK_UNCONFIRMED'},503)
        return await run_in_threadpool(operation)

    @app.get('/api/snapshot')
    def snapshot():
        pid=node.binding['semantic_project_id'];module=node.binding['module_snapshot']
        with Session(engine) as db,db.begin():
            from .secure.transport_pg import locked
            _,history=locked(db,node.binding['opaque_project_id'])
            # Trust -> Project, matching commands and receiving; one consistent status view.
            from .kernel import lock_project
            lock_project(db,pid)
            keys=set(db.execute(select(RecordWork.object_type,RecordWork.object_id).where(RecordWork.project_id==pid)).all())
            keys.update(db.execute(select(ObjectRevision.object_type,ObjectRevision.object_id).where(ObjectRevision.project_id==pid)).all())
            records=[];objects=[]
            for kind,oid in sorted(keys):
                if kind not in ('ResearchRun','Note'):continue
                view=read_record(db,pid,kind,oid);records.append({'object_id':oid,'object_type':kind,**view,'sync_status':record_status(db,node,kind,oid,history[-1])})
                from .pc_records import displayed_document
                work=view['work'];doc=displayed_document(view)
                if doc is not None:objects.append(local_object(kind,oid,pid,doc,work['version'] if work else 0))
            outboxes=list(db.scalars(select(Outbox).where(Outbox.project_id==pid)))
            status=project_status(db,pid)
        local={'identity':{'id':'identity','workspace_id':pid,'device_id':node.owner.device_id,
                          'scope':'SYNTHETIC_QA','authorization':'none'},
            'projects':[{'id':pid,'route_alias':{'ice-sonocuring':'ice'}.get(module['id'],module['id']),
                'title':'SYNTHETIC PC '+module['name'],'scope':'SYNTHETIC','module_id':module['id'],
                'module_version':module['version'],'module_snapshot':module,
                'module_hash':node.binding['local_module_hash']['value'],'local_format_version':1}],
            'objects':objects,'operations':[],'audit':[],'drafts':[]}
        return {'snapshot':local,'records':records,'project_status':status,
                'outbox_count':len(outboxes),'transport':'MANUAL_AVAILABLE','pairing':'OWNER_TEXT_V1'}

    @app.post('/api/command')
    async def command(request:Request):
        from packages.secure_wire.canonical import strict_loads
        try:data=strict_loads(await request.body())
        except ValueError:return JSONResponse({'error':'INVALID_JSON'},422)
        with Session(engine) as db,db.begin():
            result=execute_command(db,node.context,node.binding['semantic_project_id'],data)
            work=db.get(RecordWork,(node.binding['semantic_project_id'],data['object_type'],data['object_id']))
            return {**result,'object':local_object(data['object_type'],data['object_id'],node.binding['semantic_project_id'],work.document,work.version)}

    @app.get('/{path:path}')
    def static(path:str):
        dist=ROOT/'storage/runtime/browser-sync-qa/pc/dist'
        if path in ('app.js','app.css','icon.svg'):target=dist/path
        elif path=='' or re.fullmatch(r'projects/(generic|hdsp|ice)(/(runs|notes)/[a-zA-Z0-9-]+)?',path):target=dist/'index.html'
        else:return JSONResponse({'error':'NOT_FOUND'},404)
        if not target.is_file():return JSONResponse({'error':'PC_BUILD_REQUIRED'},503)
        return FileResponse(target)
    return app

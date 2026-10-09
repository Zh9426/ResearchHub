"""Isolated PC QA work copies and ordinary draft commands. Never product reads."""
import copy
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import Boolean, Integer, String, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from pydantic import ConfigDict

from .. import models as domain, service
from ..modules import load_modules
from ..schemas import RunInput, NoteInput
from .authority import protected, resolve_principal
from .canonical import digest
from .kernel import apply_in_session, heads, lock_project
from .models import ObjectRevision, Outbox
from .projection import object_view, history
from .protocol import ProtocolError, _uuid, _payload
from .secure.transport_pg import guard

class PcBase(DeclarativeBase):
    pass

class WireRunInput(RunInput):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=False)

class WireNoteInput(NoteInput):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=False)

class RecordWork(PcBase):
    __tablename__ = 'qa_record_work'
    project_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    object_type: Mapped[str] = mapped_column(String(32), primary_key=True)
    object_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document: Mapped[dict] = mapped_column(JSONB)
    version: Mapped[int] = mapped_column(Integer)
    base_heads: Mapped[list] = mapped_column(JSONB)
    last_local_tx: Mapped[str | None] = mapped_column(String(36), nullable=True)
    pending: Mapped[bool] = mapped_column(Boolean, default=True)

class RecordCommand(PcBase):
    __tablename__ = 'qa_record_commands'
    command_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36))
    principal_id: Mapped[str] = mapped_column(String(36))
    action_digest: Mapped[str] = mapped_column(String(64))
    transaction_id: Mapped[str] = mapped_column(String(36), unique=True)
    result: Mapped[dict] = mapped_column(JSONB)

def reject(code, message):
    raise ProtocolError(code, message)

def read_record(db, project_id, object_type, object_id):
    guard(db.get_bind())
    work=db.get(RecordWork,(project_id,object_type,object_id))
    return {'work':None if work is None else {'document':copy.deepcopy(work.document),
        'version':work.version,'base_heads':work.base_heads,'last_local_tx':work.last_local_tx,'pending':work.pending},
        'trusted':object_view(db,project_id,object_type,object_id),
        'history':[{'revision':r.revision,'transaction_id':r.transaction_id,'document':r.document,
                    'parents':r.parents} for r in history(db,project_id,object_type,object_id)]}

def execute_command(db, context, project_id, command, *, fault=None):
    guard(db.get_bind())
    command=copy.deepcopy(command)
    required={'command_id','transaction_id','object_id','object_type','operation','expected_work_version','expected_heads','patch'}
    if type(command) is not dict or set(command)!=required:reject('INVALID_COMMAND','exact command fields required')
    for f in ('command_id','transaction_id','object_id'):_uuid(command[f])
    kind=command['object_type']; operation=command['operation']; patch=command['patch']
    if kind not in ('ResearchRun','Note') or operation not in ('create','update','highlight'):
        reject('QA_SCOPE','ordinary Run/Note drafts only')
    if type(command['expected_work_version']) is not int or command['expected_work_version']<0:
        reject('INVALID_COMMAND','work version must be nonnegative')
    if type(command['expected_heads']) is not list or command['expected_heads']!=sorted(set(command['expected_heads'])):
        reject('INVALID_COMMAND','sorted exact heads required')
    _payload(kind,patch,2)
    if operation=='highlight' and (kind!='ResearchRun' or set(patch)!={'is_highlighted','highlight_type','highlight_note'}):
        reject('QA_SCOPE','highlight requires exactly three fields')
    state=lock_project(db,project_id)
    principal=resolve_principal(db,context,project_id)
    action_digest=digest(command)
    previous=db.get(RecordCommand,command['command_id'])
    if previous:
        if (previous.project_id!=project_id or previous.principal_id!=principal.principal_id
                or previous.action_digest!=action_digest):reject('IDENTITY_COLLISION','command identity collision')
        result=copy.deepcopy(previous.result)
        outbox=db.get(Outbox,previous.transaction_id)
        if outbox is None:reject('OUTBOX_MISSING','committed command outbox missing')
        result['receipt']=apply_in_session(db,outbox.envelope,context,local_outbox=True)
        return result
    if db.get(Outbox,command['transaction_id']):reject('IDENTITY_COLLISION','transaction identity collision')
    oid=command['object_id']; key=(project_id,kind,oid)
    work=db.scalar(select(RecordWork).where(RecordWork.project_id==project_id,
        RecordWork.object_type==kind,RecordWork.object_id==oid).with_for_update())
    current_heads=heads(db,*key)
    if (work.version if work else 0)!=command['expected_work_version']:reject('WORK_CAS','work version changed')
    if current_heads!=command['expected_heads']:reject('HEADS_CAS','trusted heads changed')
    view=object_view(db,*key)
    if operation=='create':
        if work or current_heads:reject('IDENTITY_COLLISION','object identity collision')
        document=copy.deepcopy(patch)
    else:
        if view['status']=='conflicted' or len(current_heads)!=1:
            reject('CONFLICT_REQUIRES_PROPOSAL','conflict requires explicit candidate proposal')
        # A pending local branch must match current heads; never transplant it onto a remote head.
        if work and work.pending and work.base_heads!=current_heads:
            reject('WORK_BASE_CHANGED','pending work and trusted baseline differ')
        base=work.document if work and work.pending else view['accepted']
        if base is None:reject('TRUSTED_BASE_REQUIRED','verified accepted baseline required')
        document={**copy.deepcopy(base),**patch}
    if protected(kind,document) or any(protected(kind,c['document']) for c in view['candidates']):
        reject('PROTECTED_DENIED','protected scientific operation is unavailable')
    if not document.get('title','').strip():reject('INVALID_COMMAND','nonblank title required')
    user=db.get(domain.User,principal.user_id)
    if user is None:reject('DOMAIN_USER_REQUIRED','registered QA user required')
    actor=SimpleNamespace(user=user,actor_type=principal.actor_type,
                          token=None if principal.actor_type=='human' else True)
    request=SimpleNamespace(state=SimpleNamespace(request_id='SYNTHETIC-PC-'+command['command_id']))
    project=service.project_for(db,actor,project_id,write=True)
    if digest(project.module_snapshot)!=state.module_snapshot_hash:reject('MODULE_FROZEN','frozen snapshot mismatch')
    collection='runs' if kind=='ResearchRun' else 'notes'
    schema=WireRunInput if kind=='ResearchRun' else WireNoteInput
    highlight_fields={'is_highlighted','highlight_type','highlight_note'}
    body={k:v for k,v in document.items() if k not in highlight_fields}
    highlight={k:v for k,v in document.items() if k in highlight_fields}
    if len(highlight.get('highlight_type',''))>100 or len(highlight.get('highlight_note',''))>10000:
        reject('INVALID_COMMAND','highlight length exceeded')
    cls=domain.ResearchRun if kind=='ResearchRun' else domain.Note
    obj=db.scalar(select(cls).where(cls.id==oid).with_for_update())
    if obj and obj.project_id!=project_id:reject('IDENTITY_COLLISION','carrier belongs to another project')
    if obj is None:
        obj=cls(id=oid,project_id=project_id)
        service.create_record_instance(db,actor,request,collection,project_id,body,load_modules(),obj,schema=schema)
    elif operation!='highlight':
        service.assert_writable(obj)
        data=service.parsed(collection,body,schema=schema)
        service.scientific_authority(actor,collection,body,existing=obj)
        service.validate_links(db,obj,data,load_modules())
        before=service.serialize(db,obj)
        service.apply_data(db,obj,data);db.flush()
        service.audit(db,actor,request,'update_'+collection,obj,before)
    if highlight:
        service.assert_writable(obj)
        before=service.serialize(db,obj)
        service.apply_data(db,obj,highlight)
        db.flush()
        service.audit(db,actor,request,'highlight_runs',obj,before)
    if fault:fault('after_domain')
    tid=command['transaction_id']; stamp=datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00','Z')
    common=dict(project_id=project_id,device_id=principal.device_id,actor_id=principal.actor_id,
                actor_type=principal.actor_type,schema_version=2,created_at=stamp)
    change=dict(**common,change_id=str(uuid4()),audit_id=str(uuid4()),transaction_id=tid,
        object_type=kind,object_id=oid,operation='create' if operation=='create' else 'update',
        parents=current_heads,payload=patch,module_snapshot_hash=state.module_snapshot_hash)
    dependencies=sorted({db.get(ObjectRevision,h).transaction_id for h in current_heads})
    tx=dict(**common,transaction_id=tid,idempotency_key=tid,protocol_version=2,
        ordered_change_ids=[change['change_id']],changes=[change],dependencies=dependencies)
    receipt=apply_in_session(db,tx,context,local_outbox=True,domain_action_digest=action_digest,fault=fault)
    after=heads(db,*key)
    if work is None:
        work=RecordWork(project_id=project_id,object_type=kind,object_id=oid,version=0)
        db.add(work)
    work.document=copy.deepcopy(document);work.version+=1;work.base_heads=after
    work.last_local_tx=tid;work.pending=True
    result={'receipt':receipt,'work_version':work.version,'heads':after,'transaction_id':tid,'object_id':oid}
    db.add(RecordCommand(command_id=command['command_id'],project_id=project_id,
        principal_id=principal.principal_id,action_digest=action_digest,transaction_id=tid,result=result))
    db.flush()
    return result

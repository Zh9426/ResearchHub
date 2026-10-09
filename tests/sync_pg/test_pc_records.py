"""PC command boundary against the real dedicated QA PostgreSQL."""
from uuid import uuid4
import pytest
from sqlalchemy.orm import Session
from researchhub import models as domain
from researchhub.sync.models import Outbox
from researchhub.sync.protocol import ProtocolError
from researchhub.sync.pc_records import PcBase, execute_command, read_record
from test_domain_outbox import domain_world

def command(kind='ResearchRun', patch=None, **extra):
    return dict(command_id=str(uuid4()), transaction_id=str(uuid4()), object_id=str(uuid4()),
                object_type=kind, operation='create', expected_work_version=0, expected_heads=[],
                patch=patch or {'title':'SYNTHETIC PC', 'run_type':'simulation'}, **extra)

def apply(world, cmd, **kwargs):
    with Session(world.engine) as db, db.begin():
        return execute_command(db, world.context(), world.project_id, cmd, **kwargs)

def test_create_retry_cas_highlight_and_note(domain_world):
    w=domain_world
    PcBase.metadata.create_all(w.engine)
    c=command(); first=apply(w,c)
    assert apply(w,c)==first
    with Session(w.engine) as db:
        assert db.get(domain.ResearchRun,c['object_id']).title=='SYNTHETIC PC'
        out=db.get(Outbox,c['transaction_id'])
        assert out.envelope['transaction']['changes'][0]['object_id']==c['object_id']
        view=read_record(db,w.project_id,'ResearchRun',c['object_id'])
        assert view['work']['version']==1 and view['trusted']['accepted']['title']=='SYNTHETIC PC'
    changed={**c,'patch':{**c['patch'],'title':'collision'}}
    with pytest.raises(ProtocolError,match='collision'):apply(w,changed)
    update={**command(),'object_id':c['object_id'],'operation':'highlight',
            'expected_work_version':1,'expected_heads':view['trusted']['heads'],
            'patch':{'is_highlighted':True,'highlight_type':'','highlight_note':'中文'}}
    apply(w,update)
    with Session(w.engine) as db:
        assert db.get(domain.ResearchRun,c['object_id']).title=='SYNTHETIC PC'
        assert db.get(domain.ResearchRun,c['object_id']).is_highlighted
    stale={**update,'command_id':str(uuid4()),'transaction_id':str(uuid4())}
    with pytest.raises(ProtocolError,match='version'):apply(w,stale)
    n=command('Note',{'title':'笔记','content':'  中文\n🧪  '})
    apply(w,n)
    with Session(w.engine) as db:assert db.get(domain.Note,n['object_id']).content=='  中文\n🧪  '

def test_rollback_and_protected_denied(domain_world):
    w=domain_world; PcBase.metadata.create_all(w.engine)
    c=command()
    def fail(point):
        if point=='after_domain':raise RuntimeError('injected')
    with pytest.raises(RuntimeError,match='injected'):apply(w,c,fault=fail)
    with Session(w.engine) as db:
        assert db.get(domain.ResearchRun,c['object_id']) is None
        assert db.get(Outbox,c['transaction_id']) is None
    c['patch']['human_conclusion']='final'
    with pytest.raises(ProtocolError,match='protected'):apply(w,c)

def test_remote_only_carrier_same_id_and_late_conflict_retry(domain_world):
    import copy
    w=domain_world;PcBase.metadata.create_all(w.engine)
    oid=str(uuid4())
    remote=w.make(kind='ResearchRun',oid=oid,payload={'title':'远端合成','run_type':'simulation'},actor='human_b')
    remote['protocol_version']=remote['schema_version']=2
    remote['changes'][0]['schema_version']=2
    w.apply(remote,actor='human_b')
    with Session(w.engine) as db:
        v=read_record(db,w.project_id,'ResearchRun',oid)
        assert db.get(domain.ResearchRun,oid) is None and v['work'] is None
    cmd={**command(),'object_id':oid,'operation':'update','expected_heads':v['trusted']['heads'],
         'patch':{'observation':'PC编辑'}}
    result=apply(w,cmd)
    with Session(w.engine) as db:
        assert db.get(domain.ResearchRun,oid).observation=='PC编辑'
        assert db.get(Outbox,cmd['transaction_id']).envelope['transaction']['changes'][0]['object_id']==oid
    branch=w.make(kind='ResearchRun',oid=oid,operation='update',parents=v['trusted']['heads'],
                  payload={'observation':'并发远端'},actor='human_b')
    branch['protocol_version']=branch['schema_version']=2;branch['changes'][0]['schema_version']=2
    w.apply(branch,actor='human_b')
    with Session(w.engine) as db:
        view=read_record(db,w.project_id,'ResearchRun',oid)
        assert view['trusted']['status']=='conflicted' and view['trusted']['accepted'] is None
        assert len(view['trusted']['candidates'])==2 and view['work']['document']['observation']=='PC编辑'
    replay=apply(w,cmd)
    assert replay['receipt']['state']=='CANDIDATE'
    assert replay['transaction_id']==result['transaction_id']

def test_exact_handoff_and_pending_read_selection(domain_world):
    from researchhub.sync.pc_records import complete_handoff, displayed_document
    w=domain_world;PcBase.metadata.create_all(w.engine)
    first=command();apply(w,first)
    with Session(w.engine) as db,db.begin():
        view=read_record(db,w.project_id,'ResearchRun',first['object_id'])
        assert displayed_document(view)==view['work']['document']
    second={**command(),'object_id':first['object_id'],'operation':'update',
            'expected_work_version':1,'expected_heads':view['trusted']['heads'],'patch':{'title':'newer'}}
    apply(w,second)
    with Session(w.engine) as db,db.begin():
        assert not complete_handoff(db,w.project_id,'ResearchRun',first['object_id'],first['transaction_id'],1)
        assert read_record(db,w.project_id,'ResearchRun',first['object_id'])['work']['pending']
        assert complete_handoff(db,w.project_id,'ResearchRun',first['object_id'],second['transaction_id'],2)
        view=read_record(db,w.project_id,'ResearchRun',first['object_id'])
        assert not view['work']['pending']
        view['work']['document']={'title':'stale copy'}
        assert displayed_document(view)==view['trusted']['accepted']
        view['trusted']['accepted']=None
        assert displayed_document(view) is None

def test_command_locks_trust_before_project_and_work(domain_world):
    from sqlalchemy import event
    w=domain_world;PcBase.metadata.create_all(w.engine);statements=[]
    def record(conn,cursor,statement,parameters,context,executemany):
        if 'FOR UPDATE' in statement:statements.append(statement)
    event.listen(w.engine,'before_cursor_execute',record)
    try:apply(w,command())
    finally:event.remove(w.engine,'before_cursor_execute',record)
    from researchhub.sync.secure.transport_pg import Trust
    assert Trust.__tablename__ in statements[0]
    assert any('qa_record_work' in s for s in statements[1:])

def test_explicit_resolution_candidate_and_frozen_cas(domain_world):
    w=domain_world;PcBase.metadata.create_all(w.engine)
    c=command('Note',{'title':'SYNTHETIC','content':'base'});created=apply(w,c)
    branches=[]
    for actor,text in [('human','local'),('human_b','remote')]:
        tx=w.make(kind='Note',oid=c['object_id'],operation='update',parents=created['heads'],payload={'content':text},actor=actor)
        tx['protocol_version']=tx['schema_version']=2;tx['changes'][0]['schema_version']=2
        w.apply(tx,actor=actor);branches.append(tx)
    with Session(w.engine) as db:view=read_record(db,w.project_id,'Note',c['object_id'])
    cmd={**command('Note'),'object_id':c['object_id'],'operation':'resolve','expected_work_version':1,'expected_heads':view['trusted']['heads'],'patch':{'title':'SYNTHETIC','content':'proposal'}}
    third=w.make(kind='Note',oid=c['object_id'],operation='update',parents=created['heads'],payload={'content':'third'},actor='human_b')
    third['protocol_version']=third['schema_version']=2;third['changes'][0]['schema_version']=2
    w.apply(third,actor='human_b')
    with pytest.raises(ProtocolError,match='heads'):apply(w,cmd)
    with Session(w.engine) as db:cmd['expected_heads']=read_record(db,w.project_id,'Note',c['object_id'])['trusted']['heads']
    result=apply(w,cmd)
    assert apply(w,cmd)['receipt']['state']=='CANDIDATE'
    assert result['receipt']['state']=='CANDIDATE'
    with Session(w.engine) as db:
        view=read_record(db,w.project_id,'Note',c['object_id'])
        assert view['trusted']['accepted'] is None and len(view['trusted']['heads'])==1
        assert db.get(Outbox,cmd['transaction_id']).envelope['transaction']['changes'][0]['operation']=='resolve'
    with pytest.raises(ProtocolError,match='version'):apply(w,{**cmd,'command_id':str(uuid4()),'transaction_id':str(uuid4())})

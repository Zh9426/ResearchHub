"""Real guarded QA PostgreSQL oracle; all synthetic rows roll back per case."""
import argparse
import copy
import json
import sys
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL
from sqlalchemy import select
from sqlalchemy.orm import Session

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'apps/api'))
from researchhub.sync.authority import TrustedContext, register_principal
from researchhub.sync.kernel import register_project, apply_in_session, _common_base
from researchhub.sync.models import initialize_qa, ProjectState, Principal, SyncTransaction, ObjectRevision, ObjectHead, Dependency, AcceptedProjection, SyncConflict, Audit, Inbox
from researchhub.sync.protocol import ProtocolError, revision
from researchhub.sync.qa import qa_engine
from researchhub.sync.record_policy import apply_record_in_session

def snapshot(db, project):
    def rows(model): return list(db.scalars(select(model).where(model.project_id==project)))
    state=db.get(ProjectState,project)
    heads={}
    for r in rows(ObjectHead): heads.setdefault(r.object_type+':'+r.object_id,[]).append(r.revision)
    return dict(project_id=project,module_hash=state.module_snapshot_hash,sequence=state.received_cursor,watermark=state.accepted_watermark,
        transactions={r.transaction_id:dict(raw=r.raw,digest=r.digest,state=r.state,receipt=db.get(Inbox,r.transaction_id).receipt) for r in rows(SyncTransaction)},
        revisions={r.revision:dict(semantic=r.semantic,document=r.document,lifecycle=r.lifecycle) for r in rows(ObjectRevision)},
        heads={k:sorted(v) for k,v in heads.items()},
        dependencies={r.transaction_id:sorted(d.depends_on for d in rows(Dependency) if d.transaction_id==r.transaction_id) for r in rows(SyncTransaction)},
        projections={r.object_type+':'+r.object_id:r.revision for r in rows(AcceptedProjection)},
        conflicts=sorted([dict(heads=r.head_set,base=r.common_base,status=r.status,candidates=r.candidate_transactions,resolution=r.resolution_revision) for r in rows(SyncConflict)],key=lambda x:json.dumps(x,sort_keys=True)),
        audits=sorted([dict(transaction_id=r.transaction_id,action=r.action,content=r.content) for r in rows(Audit)],key=lambda x:json.dumps(x,sort_keys=True)))

def run(fixture):
    engine=qa_engine();initialize_qa(engine);results=[]
    try:
        for case in fixture['cases']:
            p=case.get('principal',fixture['principal']);project=p['project_id'];steps=[]
            with Session(engine) as db:
                # Do not commit any fixture state or mutate an existing project.
                if db.get(ProjectState,project) is not None: raise RuntimeError('FIXTURE_PROJECT_ALREADY_EXISTS')
                register_project(db,project,fixture['module_hash'])
                register_principal(db,**{k:v for k,v in p.items() if k!='active'},user_id=p['actor_id'],session_id=p['principal_id'])
                for item in case['steps']:
                    if item.get('revoke'): db.get(Principal,p['principal_id']).active=False;db.flush()
                    new_project=item.get('target_project',item.get('context_project'))
                    if new_project:
                        register_project(db,new_project,fixture['module_hash'])
                        db.get(Principal,p['principal_id']).project_id=new_project;db.flush()
                    before=snapshot(db,project)
                    try:
                        with db.begin_nested():
                            receipt=apply_record_in_session(db,copy.deepcopy(item['transaction']),TrustedContext(p['principal_id'],mode=item.get('mode','online')),item.get('module',fixture['module']),project_id=project)
                            db.flush()
                        result={'result':receipt['state'],'receipt':receipt}
                    except ProtocolError as error:
                        result={'result':error.code}
                        assert snapshot(db,project)==before, 'failed step mutated persisted state'
                    result['snapshot']=snapshot(db,project);steps.append(result)
                results.append({'name':case['name'],'steps':steps})
                db.rollback()
    finally: engine.dispose()
    return results

def run_common_base(fixture):
    """Build historical DAG using real Kernel transactions, never SQL fixtures.

    Historical offline proposals intentionally use the existing Kernel contract;
    the new record-policy admission must still reject such a stale new proposal.
    """
    engine=qa_engine();initialize_qa(engine);p=fixture['principal'];result=[]
    try:
        for probe in fixture['common_base']:
            with Session(engine) as db:
                if db.get(ProjectState,p['project_id']) is not None: raise RuntimeError('FIXTURE_PROJECT_ALREADY_EXISTS')
                register_project(db,p['project_id'],fixture['module_hash'])
                register_principal(db,**{k:v for k,v in p.items() if k!='active'},user_id=p['actor_id'],session_id=p['principal_id'])
                revisions={}
                template=fixture['cases'][1]['steps'][0]['transaction']
                for name,parents in probe['graph'].items():
                    tx=copy.deepcopy(template);tid=str(uuid5(NAMESPACE_URL,'C1-common-base-tx-'+name));c=tx['changes'][0]
                    tx['transaction_id']=tx['idempotency_key']=c['transaction_id']=tid
                    c['change_id']=str(uuid5(NAMESPACE_URL,'C1-common-base-change-'+name));c['audit_id']=str(uuid5(NAMESPACE_URL,'C1-common-base-audit-'+name));tx['ordered_change_ids']=[c['change_id']]
                    c['parents']=sorted(revisions[parent] for parent in parents);c['operation']='create' if not parents else 'resolve' if len(parents)>1 else 'update';c['payload']={'title':'SYNTHETIC','content':name}
                    apply_in_session(db,tx,TrustedContext(p['principal_id'],mode='offline_proposal' if len(parents)>1 else 'online'));db.flush();revisions[name]=revision(c)
                answer=_common_base(db,[revisions[name] for name in probe['heads']]);result.append(next((name for name,r in revisions.items() if r==answer),None))
                db.rollback()
    finally: engine.dispose()
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    target=Path(args.output).resolve();allowed=(ROOT/'storage/runtime/browser-sync-qa').resolve()
    if not target.is_relative_to(allowed) or target.exists(): raise RuntimeError('NEW_QA_OUTPUT_REQUIRED')
    fixture=json.loads((ROOT/'fixtures/sync/v2/record_kernel_cases.json').read_text(encoding='utf-8'))
    result=run(fixture);bases=run_common_base(fixture);assert bases==[p['expected'] for p in fixture['common_base']]
    target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    target.with_name('common-base.json').write_text(json.dumps(bases),encoding='utf-8')
    mismatches=[(case['name'],i,item['expected'],got['result']) for case,actual in zip(fixture['cases'],result) for i,(item,got) in enumerate(zip(case['steps'],actual['steps'])) if item['expected']!=got['result']]
    print(json.dumps({'cases':len(result),'mismatches':mismatches}));sys.exit(bool(mismatches))

"""Synthetic v2 transcripts. This author does not import either kernel."""
import copy
import hashlib
import json
from pathlib import Path

def uid(n): return f'10000000-0000-4000-8000-{n:012x}'
def digest(x): return hashlib.sha256(json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
PROJECT=uid(1)
MODULE={'id':'synthetic-record-kernel','run_types':[{'id':'experiment'}],'context_fields':[]}
PRINCIPAL={'principal_id':uid(2),'project_id':PROJECT,'device_id':uid(3),'actor_id':uid(4),'actor_type':'human','active':True}
def tx(n, *, parents=(), operation='create', payload=None, oid=10, kind='Note', dependencies=()):
    c=dict(change_id=uid(n+10000),audit_id=uid(n+20000),transaction_id=uid(n),project_id=PROJECT,device_id=uid(3),actor_id=uid(4),actor_type='human',object_id=uid(oid),object_type=kind,operation=operation,parents=sorted(parents),payload=payload or {'title':'SYNTHETIC','content':'原文  '},schema_version=2,module_snapshot_hash=digest(MODULE),created_at='2026-10-09T01:02:03.004Z')
    return dict(transaction_id=uid(n),idempotency_key=uid(n),project_id=PROJECT,device_id=uid(3),actor_id=uid(4),actor_type='human',protocol_version=2,schema_version=2,created_at=c['created_at'],changes=[c],ordered_change_ids=[c['change_id']],dependencies=sorted(dependencies))
def rev(t): return digest(t['changes'][0])
def step(t, expected='ACCEPTED', **extra): return {'transaction':t,'expected':expected,**extra}
def build():
    base=tx(100);a=tx(101,parents=[rev(base)],operation='update',payload={'content':'local'});b=tx(102,parents=[rev(base)],operation='update',payload={'content':'remote'})
    resolve=tx(103,parents=[rev(a),rev(b)],operation='resolve',payload={'content':'reviewed'})
    third=tx(104,parents=[rev(base)],operation='update',payload={'content':'third'})
    cases=[]
    def add(name,steps): cases.append({'name':name,'steps':steps})
    run=tx(110,kind='ResearchRun',payload={'title':'SYNTHETIC run','run_type':'experiment','status':'planned','context_data':{},'is_highlighted':False})
    update=tx(111,kind='ResearchRun',parents=[rev(run)],operation='update',payload={'observation':'保留空白  '})
    star=tx(112,kind='ResearchRun',parents=[rev(update)],operation='update',payload={'is_highlighted':True,'highlight_type':'重点','highlight_note':'合成'})
    add('create-update-star',[step(run),step(update),step(star),step(star)])
    add('same-base-ab',[step(base),step(a),step(b,'CANDIDATE'),step(a,'CANDIDATE')])
    add('same-base-ba',[step(base),step(b),step(a,'CANDIDATE')])
    add('independent',[step(base),step(tx(120,oid=11))])
    add('ordinary-offline-proposal',[step(base,'CANDIDATE',mode='offline_proposal'),step(base,'CANDIDATE')])
    batch=copy.deepcopy(a);c=tx(121,oid=11)['changes'][0];c['transaction_id']=batch['transaction_id'];batch['changes'].append(c);batch['ordered_change_ids'].append(c['change_id'])
    child=tx(122,oid=12,dependencies=[batch['transaction_id']]);grandchild=tx(123,oid=13,dependencies=[child['transaction_id']])
    add('late-batch-recursive',[step(base),step(batch),step(child),step(grandchild),step(tx(124,oid=14)),step(b,'CANDIDATE'),step(batch,'CANDIDATE')])
    add('proposal-echo',[step(base),step(a),step(b,'CANDIDATE'),step(resolve,'CANDIDATE'),step(resolve,'CANDIDATE')])
    add('stale-proposal',[step(base),step(a),step(b,'CANDIDATE'),step(third,'CANDIDATE'),step(resolve,'CONFLICT_CHANGED')])
    incomplete=tx(130,parents=[rev(a),rev(b)],operation='resolve',payload={'title':'review'})
    add('incomplete-review',[step(base),step(a),step(b,'CANDIDATE'),step(incomplete,'REVIEW_INCOMPLETE')])
    add('missing-parent',[step(tx(140,operation='update',parents=['f'*64]),'DEPENDENCY_REQUIRED')])
    add('missing-dependency',[step(tx(141,dependencies=[uid(999)]),'DEPENDENCY_REQUIRED')])
    add('cross-object',[step(base),step(tx(142,oid=11,operation='update',parents=[rev(base)]),'CROSS_OBJECT_PARENT')])
    collision=copy.deepcopy(base);collision['changes'][0]['payload']['content']='collision'
    add('transaction-collision',[step(base),step(collision,'IDENTITY_COLLISION')])
    change=tx(143,oid=11);change['changes'][0]['change_id']=base['changes'][0]['change_id'];change['ordered_change_ids']=[change['changes'][0]['change_id']]
    audit=tx(144,oid=12);audit['changes'][0]['audit_id']=base['changes'][0]['audit_id']
    add('change-audit-collision',[step(base),step(change,'IDENTITY_COLLISION'),step(audit,'IDENTITY_COLLISION')])
    forged=copy.deepcopy(base);forged['actor_id']=uid(999);forged['changes'][0]['actor_id']=uid(999)
    add('principal-mismatch',[step(forged,'ACTOR_CONTEXT_MISMATCH')])
    add('revoked-echo',[step(base),step(base,'PRINCIPAL_REVOKED',revoke=True)])
    frozen=copy.deepcopy(base);frozen['changes'][0]['module_snapshot_hash']='f'*64
    add('module-mismatch',[step(frozen,'MODULE_FROZEN')])
    add('protected',[step(tx(145,kind='ResearchRun',payload={'human_conclusion':'not authorized'}),'HUMAN_REQUIRED')])
    for actor in ['codex','chatgpt','system']:
        ai_base=copy.deepcopy(run);ai_base['actor_type']=actor;ai_base['changes'][0]['actor_type']=actor
        ai_update=tx(146,kind='ResearchRun',parents=[rev(ai_base)],operation='update',payload={'human_conclusion':''})
        ai_update['actor_type']=actor;ai_update['changes'][0]['actor_type']=actor
        add('ai-empty-conclusion-'+actor,[step(ai_base),step(ai_update,'HUMAN_REQUIRED')])
        cases[-1]['principal']={**PRINCIPAL,'actor_type':actor}
    add('cross-project-principal',[step(base,'ACTOR_CONTEXT_MISMATCH',context_project=uid(999))])
    project_b=copy.deepcopy(tx(150));project_b['project_id']=uid(888);project_b['changes'][0]['project_id']=uid(888)
    add('state-project-pin',[step(base),step(project_b,'PROJECT_REQUIRED',target_project=uid(888))])
    other_module={**MODULE,'id':'other-synthetic-module'};module_b=tx(151,oid=11);module_b['changes'][0]['module_snapshot_hash']=digest(other_module)
    add('state-module-pin',[step(base),step(module_b,'MODULE_FROZEN',module=other_module,module_hash=digest(other_module))])
    # A legal historical offline fork can be received from older trusted kernel
    # history. Graph-only common-base probes do not grant stale resolve admission.
    graph={'a':[],'b':['a'],'c':['a'],'d':['b','c'],'e':['b','c'],'f':['d'],'g':['d']}
    return {'version':1,'module':MODULE,'module_hash':digest(MODULE),'principal':PRINCIPAL,'cases':cases,'common_base':[{'graph':graph,'heads':['b','c'],'expected':'a'},{'graph':graph,'heads':['f','g'],'expected':'d'},{'graph':graph,'heads':['d','e'],'expected':None}]}
if __name__=='__main__':
    path=Path(__file__).resolve().parents[2]/'fixtures/sync/v2/record_kernel_cases.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(build(),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

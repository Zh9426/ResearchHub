"""Narrow trusted QA record policy; never selected by a wire payload."""
from copy import deepcopy
from dataclasses import replace
from .authority import principal_for, protected
from .canonical import digest
from .kernel import apply_in_session, lock_project, heads, _materialize
from .models import SyncTransaction, ObjectRevision
from .protocol import validate_transaction, ProtocolError
from .qa import assert_qa_bind

def apply_record_in_session(db, tx, context, module_snapshot, *, project_id):
    assert_qa_bind(db.get_bind())
    tx=deepcopy(tx);validate_transaction(tx)
    if tx['project_id']!=project_id:
        raise ProtocolError('PROJECT_REQUIRED','record receiver project pin mismatch')
    project=lock_project(db,project_id)
    if digest(module_snapshot)!=project.module_snapshot_hash:
        raise ProtocolError('MODULE_FROZEN','record receiver module pin mismatch')
    principal_for(db,context,tx,replay=True)
    # Exact echo is checked by the original kernel before the new-head policy.
    if db.get(SyncTransaction,tx['transaction_id']) is not None:
        return apply_in_session(db,tx,context)
    if tx['protocol_version']!=2 or tx['schema_version']!=2:
        raise ProtocolError('RECORD_SCOPE_REQUIRED','only v2 Run/Note records')
    if digest(module_snapshot)!=project.module_snapshot_hash or any(c['module_snapshot_hash']!=project.module_snapshot_hash for c in tx['changes']):
        raise ProtocolError('MODULE_FROZEN','frozen module snapshot mismatch')
    resolving=any(c['operation']=='resolve' for c in tx['changes'])
    if resolving and not all(c['operation']=='resolve' for c in tx['changes']):
        raise ProtocolError('RECORD_SCOPE_REQUIRED','resolution policy applies to the entire transaction')
    for c in tx['changes']:
        if c['object_type'] not in {'ResearchRun','Note'}:
            raise ProtocolError('RECORD_SCOPE_REQUIRED','ordinary record scope required')
        hs=heads(db,tx['project_id'],c['object_type'],c['object_id'])
        if resolving and c['parents']!=hs:
            raise ProtocolError('CONFLICT_CHANGED','new proposal must name exact current heads')
        parents=[db.get(ObjectRevision,p) for p in c['parents']]
        if any(p is None for p in parents):
            raise ProtocolError('DEPENDENCY_REQUIRED','missing parent')
        if any((p.project_id,p.object_type,p.object_id)!=(c['project_id'],c['object_type'],c['object_id']) for p in parents):
            raise ProtocolError('CROSS_OBJECT_PARENT','parent scope differs')
        document,_=_materialize(c,parents)
        if c['operation']=='restore' or protected(c['object_type'],document) or any(protected(c['object_type'],p.document) for p in parents+[db.get(ObjectRevision,h) for h in hs]):
            raise ProtocolError('HUMAN_REQUIRED','record policy cannot authorize protected changes')
    return apply_in_session(db,tx,replace(context,mode='offline_proposal' if resolving else context.mode,grant_id=None))

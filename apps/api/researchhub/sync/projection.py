"""Queries separate immutable candidates from current accepted projection."""

from sqlalchemy import select

from .kernel import heads
from .models import (
    AcceptedProjection,
    Inbox,
    ObjectRevision,
    ProjectState,
    SyncConflict,
    SyncTransaction,
)


def object_view(db, project_id, object_type, object_id):
    key = (project_id, object_type, object_id)
    head_set = heads(db, *key)
    candidates = [db.get(ObjectRevision, h) for h in head_set]
    accepted = db.get(AcceptedProjection, key)
    conflict = db.scalar(select(SyncConflict).where(SyncConflict.project_id == project_id,
                         SyncConflict.object_type == object_type, SyncConflict.object_id == object_id,
                         SyncConflict.status.in_(['open', 'resolving'])))
    trashed = any(r.lifecycle == 'trashed' for r in candidates)
    return {'project_id': project_id, 'object_type': object_type, 'object_id': object_id,
            'status': 'conflicted' if conflict else 'accepted' if accepted else 'candidate',
            'heads': head_set, 'candidate_count': len(candidates),
            'candidates': [{'revision': r.revision, 'transaction_id': r.transaction_id,
                            'device_id':r.semantic['device_id'],'actor_id':r.semantic['actor_id'],
                            'state':db.get(SyncTransaction,r.transaction_id).state,
                            'document': r.document, 'lifecycle': r.lifecycle} for r in candidates],
            'base': db.get(ObjectRevision, conflict.common_base).document if conflict and conflict.common_base else None,
            'base_revision': conflict.common_base if conflict else None,
            'accepted': accepted.document if accepted and not conflict else None,
            'accepted_revision': accepted.revision if accepted and not conflict else None,
            'lifecycle': 'trashed' if trashed else accepted.lifecycle if accepted else 'active',
            'visible': not trashed and accepted is not None and conflict is None}


def project_status(db, project_id):
    project = db.get(ProjectState, project_id, populate_existing=True)
    receipts = list(db.execute(select(Inbox.sequence, SyncTransaction.state).join(
        SyncTransaction, SyncTransaction.transaction_id == Inbox.transaction_id).where(
            Inbox.project_id == project_id).order_by(Inbox.sequence)))
    return {'received_cursor': project.received_cursor, 'accepted_watermark': project.accepted_watermark,
            'fully_synced': project.received_cursor == project.accepted_watermark,
            'receipts': [{'sequence': sequence, 'state': state} for sequence, state in receipts]}


def history(db, project_id, object_type, object_id):
    return list(db.scalars(select(ObjectRevision).where(ObjectRevision.project_id == project_id,
                          ObjectRevision.object_type == object_type, ObjectRevision.object_id == object_id)))

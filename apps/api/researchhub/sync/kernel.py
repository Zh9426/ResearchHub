"""QA PostgreSQL transaction engine. No import-time connections or product writes.

Existing immutable parents must be present before their child is inserted. Together
with content-addressed identity and immutable parent edges this topological insertion
rule excludes cycles: no previously stored ancestor can be rewritten to point back.
"""

from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from .artifacts import validate_artifact
from .authority import assert_domain_ai_scope, consume_grant, principal_for, protected
from .canonical import digest
from .models import (
    AcceptedProjection,
    Audit,
    Dependency,
    Inbox,
    ObjectHead,
    ObjectRevision,
    Outbox,
    ProjectState,
    RevisionParent,
    SyncConflict,
    SyncTransaction,
    TransactionMember,
)
from .protocol import ProtocolError, _payload, revision, validate_transaction
from .qa import assert_qa_bind

CRASH_POINTS = ('after_revision_insert', 'after_conflict_create',
                'after_domain_projection', 'after_audit_append',
                'before_inbox_commit', 'before_cursor_advance')
TEXT_MERGE = 'NOT_IMPLEMENTED'
TAG_OR_SET = 'NOT_IMPLEMENTED'


def register_project(db, project_id, module_snapshot_hash):
    from .protocol import _hash, _uuid
    _uuid(project_id)
    _hash(module_snapshot_hash)
    existing = db.get(ProjectState, project_id)
    if existing:
        if existing.module_snapshot_hash != module_snapshot_hash:
            raise ProtocolError('MODULE_FROZEN', 'project binding is frozen')
        return existing
    row = ProjectState(project_id=project_id, module_snapshot_hash=module_snapshot_hash,
                       received_cursor=0, accepted_watermark=0)
    db.add(row)
    db.flush()
    return row


def lock_project(db, project_id):
    row = db.scalar(select(ProjectState).where(ProjectState.project_id == project_id)
                    .with_for_update().execution_options(populate_existing=True))
    if row is None:
        raise ProtocolError('PROJECT_REQUIRED', 'registered frozen project is required')
    return row


def heads(db, project_id, object_type, object_id):
    return list(db.scalars(select(ObjectHead.revision).where(
        ObjectHead.project_id == project_id, ObjectHead.object_type == object_type,
        ObjectHead.object_id == object_id).order_by(ObjectHead.revision)))


def _where(model, key):
    project_id, object_type, object_id = key
    return (model.project_id == project_id, model.object_type == object_type,
            model.object_id == object_id)


def _fault(fault, point):
    if callable(fault):
        fault(point)
    elif fault == point:
        raise RuntimeError('injected crash: ' + point)


def _envelope(value):
    if type(value) is not dict:
        raise ProtocolError('INVALID_ENVELOPE', 'object envelope required')
    if 'transaction' not in value:
        return value, {'transaction': value, 'digest': digest(value), 'commit_marker': 'COMMIT'}
    allowed = {'transaction', 'digest', 'commit_marker', 'nonce', 'signature', 'key_epoch',
               'ciphertext_metadata', 'receipt'}
    if not set(value) <= allowed or not {'transaction', 'digest', 'commit_marker'} <= set(value):
        raise ProtocolError('INVALID_ENVELOPE', 'unknown or missing envelope fields')
    if value['commit_marker'] != 'COMMIT' or value['digest'] != digest(value['transaction']):
        raise ProtocolError('INCOMPLETE_TRANSACTION', 'digest/COMMIT integrity failed')
    return value['transaction'], value


def _validate_wire(tx):
    try:
        validate_transaction(tx)
        return False
    except ProtocolError as exc:
        if exc.code != 'UPGRADE_REQUIRED':
            raise
        # Unknown versions can be retained, but every known structural field is
        # still validated; no field is dropped or interpreted as accepted state.
        probe = deepcopy(tx)
        probe['protocol_version'] = probe['schema_version'] = 1
        for c in probe.get('changes', []):
            c['schema_version'] = 1
        validate_transaction(probe)
        return True


def append_audit(db, *, audit_id, project_id, transaction_id, action, content):
    body = {'project_id': project_id, 'transaction_id': transaction_id,
            'action': action, 'content': content}
    checksum = digest(body)
    old = db.get(Audit, audit_id)
    if old:
        if old.digest != checksum:
            raise ProtocolError('IDENTITY_COLLISION', 'audit id has different content')
        return old
    row = Audit(audit_id=audit_id, project_id=project_id, transaction_id=transaction_id,
                action=action, content=content, digest=checksum)
    db.add(row)
    db.flush()
    return row


def _ancestry(db, revision_ids):
    found, frontier = {}, set(revision_ids)
    while frontier:
        rows = list(db.scalars(select(ObjectRevision).where(ObjectRevision.revision.in_(frontier))))
        frontier = set()
        for row in rows:
            if row.revision not in found:
                found[row.revision] = row
                frontier.update(p for p in row.parents if p not in found)
    return found


def _common_base(db, head_set):
    lineages = [_ancestry(db, [h]) for h in head_set]
    common = set.intersection(*(set(a) for a in lineages)) if lineages else set()
    # Common ancestors maximal by DAG ancestry, never by time or transport order.
    nonmaximal = set()
    for key in common:
        nonmaximal.update(p for p in lineages[0][key].parents if p in common)
    maxima = sorted(common - nonmaximal)
    return maxima[0] if len(maxima) == 1 else None


def _materialize(change, parents):
    patch = change['payload']
    if not parents:
        document, lifecycle = {}, 'active'
    elif len(parents) == 1:
        document, lifecycle = dict(parents[0].document), parents[0].lifecycle
    else:
        document = {}
        keys = set().union(*(set(p.document) for p in parents))
        missing = object()
        for key in keys:
            values = [p.document.get(key, missing) for p in parents]
            if all(v == values[0] for v in values) and values[0] is not missing:
                document[key] = values[0]
            elif key not in patch:
                raise ProtocolError('REVIEW_INCOMPLETE', 'all divergent payload fields need explicit review')
        lifecycle = ('trashed' if any(p.lifecycle == 'trashed' for p in parents)
                     else 'archived' if any(p.lifecycle == 'archived' for p in parents) else 'active')
    document.update(patch)
    # A legal partial patch can become invalid after inheriting its type/fields.
    _payload(change['object_type'], document, change['schema_version'])
    operation = change['operation']
    if operation in {'trash', 'archive', 'restore'}:
        lifecycle = {'trash': 'trashed', 'archive': 'archived', 'restore': 'active'}[operation]
    return document, lifecycle


REFERENCES = {
    'run_id': 'ResearchRun', 'parent_run_id': 'ResearchRun', 'linked_run_id': 'ResearchRun',
    'linked_artifact_id': 'Artifact', 'evidence_ids': 'Evidence', 'run_ids': 'ResearchRun',
    'artifact_ids': 'Artifact',
}


def _relationships(db, project_id, items):
    by_key = {(c['object_type'], c['object_id']): (c, d, lifecycle) for c, _, d, lifecycle in items}
    dependencies = set()
    run_parents = {}
    relationship_blocked = False

    def reference(kind, object_id):
        nonlocal relationship_blocked
        if (kind, object_id) in by_key:
            if by_key[(kind, object_id)][2] != 'active':
                relationship_blocked = True
            return by_key[(kind, object_id)][1]
        refs = heads(db, project_id, kind, object_id)
        if not refs:
            raise ProtocolError('RELATIONSHIP_REQUIRED', 'same-project relationship endpoint missing/wrong type')
        rows = [db.get(ObjectRevision, ref) for ref in refs]
        if len(rows) != 1 or any(row.lifecycle != 'active' for row in rows):
            relationship_blocked = True
        dependencies.update(r.transaction_id for r in rows)
        return rows[0].document if len(rows) == 1 else None

    for c, _, doc, _ in items:
        for field, kind in REFERENCES.items():
            value = doc.get(field)
            if value is None:
                continue
            for oid in value if field.endswith('_ids') else [value]:
                reference(kind, oid)
        if c['object_type'] == 'Gate':
            for criterion in doc.get('criteria', []):
                for oid in criterion.get('evidence_ids', []):
                    reference('Evidence', oid)
        if c['object_type'] == 'ResearchRun':
            run_parents[c['object_id']] = doc.get('parent_run_id')
    # Traverse parent-Run links, including internal members and existing history.
    for oid in run_parents:
        seen, current = set(), oid
        while current:
            if current in seen:
                raise ProtocolError('DEPENDENCY_CYCLE', 'Parent Run cycle')
            seen.add(current)
            if current in run_parents:
                current = run_parents[current]
            else:
                doc = reference('ResearchRun', current)
                if doc is None:
                    break
                current = doc.get('parent_run_id')
    return dependencies, relationship_blocked


def _review_scope(db, tx, head_sets):
    original_transactions = set()
    changed = {(c['object_type'], c['object_id']) for c in tx['changes']}
    for c in tx['changes']:
        if c['operation'] != 'resolve':
            continue
        hs = head_sets[(c['object_type'], c['object_id'])]
        rows = _ancestry(db, hs)
        original_transactions.update(r.transaction_id for r in rows.values()
                                     if db.get(SyncTransaction, r.transaction_id).state == 'CANDIDATE')
    required = set()
    if original_transactions:
        required = {(m.object_type, m.object_id) for m in db.scalars(select(TransactionMember).where(
            TransactionMember.transaction_id.in_(original_transactions)))}
    if not required <= changed or any(c['operation'] != 'resolve' for c in tx['changes']
                                     if (c['object_type'], c['object_id']) in required):
        raise ProtocolError('REVIEW_INCOMPLETE', 'review must explicitly cover every affected batch member')
    return original_transactions


def _invalidate(db, project_id, transaction_ids, causing_transaction):
    pending, affected = set(transaction_ids), set()
    while pending:
        fresh = pending - affected
        if not fresh:
            break
        affected.update(fresh)
        pending = set(db.scalars(select(Dependency.transaction_id).where(Dependency.depends_on.in_(fresh))))
    for transaction_id in affected:
        row = db.get(SyncTransaction, transaction_id)
        if row.state == 'ACCEPTED':
            append_audit(db, audit_id=str(uuid4()), project_id=project_id,
                         transaction_id=transaction_id, action='invalidate_sync_projection',
                         content={'caused_by': causing_transaction})
        if row.state != 'QUARANTINED':
            row.state = 'CANDIDATE'
    if affected:
        db.execute(delete(AcceptedProjection).where(AcceptedProjection.transaction_id.in_(affected)))
    db.flush()
    return affected


def _refresh_watermark(db, project):
    first_blocked = db.scalar(select(func.min(Inbox.sequence)).join(
        SyncTransaction, Inbox.transaction_id == SyncTransaction.transaction_id).where(
            Inbox.project_id == project.project_id,
            SyncTransaction.state.not_in(['ACCEPTED', 'SUPERSEDED'])))
    project.accepted_watermark = (first_blocked - 1 if first_blocked is not None
                                  else project.received_cursor)


def _receipt(db, project, tx, envelope, context, state, fault, local_outbox, domain_action_digest=None):
    sequence = context.relay_seq if context.relay_seq is not None else project.received_cursor + 1
    if type(sequence) is not int or sequence != project.received_cursor + 1:
        raise ProtocolError('CURSOR_GAP', 'received batch sequence must be contiguous')
    receipt = {'transaction_id': tx['transaction_id'], 'digest': digest(tx),
               'state': state, 'receipt_state': state, 'sequence': sequence}
    _fault(fault, 'before_inbox_commit')
    db.add(Inbox(transaction_id=tx['transaction_id'], project_id=tx['project_id'],
                 sequence=sequence, digest=digest(tx), receipt=receipt))
    if local_outbox:
        db.add(Outbox(transaction_id=tx['transaction_id'], project_id=tx['project_id'],
                      digest=digest(tx), action_digest=domain_action_digest,
                      envelope=envelope, state='LOCAL_COMMITTED'))
    db.flush()
    _fault(fault, 'before_cursor_advance')
    project.received_cursor = sequence
    _refresh_watermark(db, project)
    db.flush()
    return receipt


def apply_in_session(db, value, context, *, fault=None, local_outbox=False, domain_action_digest=None):
    """Validate/apply/flush in caller's Session transaction; NEVER commits.

    Caller must rollback on any exception. Domain adapter takes this project's
    lock before product Domain locks to maintain one shared lock order.
    """
    assert_qa_bind(db.get_bind())
    # A caller-owned dict must not change the checked identity between flushes.
    tx, envelope = _envelope(deepcopy(value))
    unknown_version = _validate_wire(tx)
    project = lock_project(db, tx['project_id'])
    checksum, transaction_id = digest(tx), tx['transaction_id']
    previous = db.get(SyncTransaction, transaction_id, populate_existing=True)
    if previous:
        principal_for(db, context, tx, replay=True)
        if previous.digest != checksum or previous.raw != tx:
            raise ProtocolError('IDENTITY_COLLISION', 'transaction id has different content')
        inbox = db.get(Inbox, transaction_id)
        return {**inbox.receipt, 'state': previous.state}
    principal = principal_for(db, context, tx)
    quarantined = unknown_version or any(c['module_snapshot_hash'] != project.module_snapshot_hash
                                        for c in tx['changes'])
    record = SyncTransaction(transaction_id=transaction_id, idempotency_key=tx['idempotency_key'],
                             project_id=tx['project_id'], digest=checksum, raw=tx,
                             state='QUARANTINED' if quarantined else 'RECEIVING', created_at=tx['created_at'])
    db.add(record)
    db.flush()
    if quarantined:
        return _receipt(db, project, tx, envelope, context, 'QUARANTINED', fault, local_outbox, domain_action_digest)

    dependencies, items, current_heads = set(tx['dependencies']), [], {}
    grant_needed = False
    for c in tx['changes']:
        rev = revision(c)
        if rev in c['parents']:
            raise ProtocolError('DEPENDENCY_CYCLE', 'revision cannot parent itself')
        old_change = db.scalar(select(ObjectRevision).where(ObjectRevision.change_id == c['change_id']))
        if old_change is not None:
            raise ProtocolError('IDENTITY_COLLISION', 'change id belongs to another transaction')
        if db.get(ObjectRevision, rev) is not None:
            raise ProtocolError('IDENTITY_COLLISION', 'revision identity already exists')
        parents = []
        for parent_id in c['parents']:
            parent = db.get(ObjectRevision, parent_id)
            if parent is None:
                raise ProtocolError('DEPENDENCY_REQUIRED', 'missing immutable parent; BASE is never fabricated')
            if (parent.project_id, parent.object_type, parent.object_id) != (
                    c['project_id'], c['object_type'], c['object_id']):
                raise ProtocolError('CROSS_OBJECT_PARENT', 'parent must have same project/object/type')
            parents.append(parent)
            dependencies.add(parent.transaction_id)
        doc, lifecycle = _materialize(c, parents)
        assert_domain_ai_scope(principal, c, parents)
        key = (c['object_type'], c['object_id'])
        hs = heads(db, tx['project_id'], *key)
        current_heads[key] = hs
        is_protected = protected(c['object_type'], doc) or any(
            protected(c['object_type'], p.document) for p in parents) or any(
            protected(c['object_type'], db.get(ObjectRevision, h).document) for h in hs)
        module_mutation = c['object_type'] == 'Project' and bool(set(c['payload']) & {
            'module_id', 'module_version', 'module_snapshot', 'module_snapshot_hash'})
        if is_protected or module_mutation or c['operation'] == 'restore' or (
                c['operation'] == 'resolve' and context.mode == 'online'):
            grant_needed = True
            if context.mode != 'online' or principal.actor_type != 'human':
                raise ProtocolError('HUMAN_REQUIRED', 'final/restore requires fresh online Human authority')
            if c['parents'] != hs:
                raise ProtocolError('CONFLICT_CHANGED', 'complete actual heads changed')
        elif c['operation'] == 'resolve':
            # Offline proposals may use a former complete set, never a subset of
            # the historical conflict they claim to resolve.
            known = db.scalar(select(SyncConflict).where(*_where(SyncConflict, (tx['project_id'], *key)),
                             SyncConflict.head_set == c['parents']))
            if len(c['parents']) > 1 and known is None:
                raise ProtocolError('CONFLICT_CHANGED', 'offline proposal did not observe a full known head set')
        if c['object_type'] == 'Artifact':
            validate_artifact(db, tx['project_id'], doc)
        items.append((c, rev, doc, lifecycle))
    reviewed = (_review_scope(db, tx, current_heads)
                if context.mode == 'online' and any(c['operation'] == 'resolve' for c in tx['changes']) else set())
    relation_dependencies, relationship_blocked = _relationships(db, tx['project_id'], items)
    dependencies.update(relation_dependencies)
    if transaction_id in dependencies:
        raise ProtocolError('DEPENDENCY_CYCLE', 'self dependency')
    for dependency in dependencies:
        dep = db.get(SyncTransaction, dependency)
        if dep is None:
            raise ProtocolError('DEPENDENCY_REQUIRED', 'transaction dependency missing')
        if dep.project_id != tx['project_id']:
            raise ProtocolError('CROSS_PROJECT_DEPENDENCY', 'dependency must share project')
    if grant_needed:
        consume_grant(db, context, principal, tx)
    for dependency in dependencies:
        db.add(Dependency(transaction_id=transaction_id, depends_on=dependency, project_id=tx['project_id']))
    for ordinal, (c, rev, doc, lifecycle) in enumerate(items):
        db.add(ObjectRevision(revision=rev, project_id=tx['project_id'], object_type=c['object_type'],
                              object_id=c['object_id'], transaction_id=transaction_id, change_id=c['change_id'],
                              parents=c['parents'], semantic=c, document=doc, lifecycle=lifecycle))
        db.flush()
        for p in c['parents']:
            db.add(RevisionParent(revision=rev, parent=p, project_id=tx['project_id'],
                                  object_type=c['object_type'], object_id=c['object_id']))
        db.add(TransactionMember(transaction_id=transaction_id, revision=rev, project_id=tx['project_id'],
                                 object_type=c['object_type'], object_id=c['object_id'], ordinal=ordinal))
        db.execute(delete(ObjectHead).where(*_where(ObjectHead, (tx['project_id'], c['object_type'], c['object_id'])),
                                           ObjectHead.revision.in_(c['parents'])))
        db.add(ObjectHead(project_id=tx['project_id'], object_type=c['object_type'], object_id=c['object_id'], revision=rev))
    db.flush()
    _fault(fault, 'after_revision_insert')
    invalidated = set()
    now = datetime.now(timezone.utc)
    for c, rev, _, _ in items:
        key = (tx['project_id'], c['object_type'], c['object_id'])
        hs = heads(db, *key)
        old_conflicts = list(db.scalars(select(SyncConflict).where(*_where(SyncConflict, key),
                                      SyncConflict.status.in_(['open', 'resolving']))))
        for old in old_conflicts:
            old.status = 'resolved' if len(hs) == 1 and c['operation'] == 'resolve' else 'superseded'
            if old.status == 'resolved':
                old.resolution_revision, old.resolved_at = rev, now
        if len(hs) > 1:
            common = _common_base(db, hs)
            ancestors = _ancestry(db, hs)
            before_base = set(_ancestry(db, [common])) if common else set()
            contenders = {r.transaction_id for rid, r in ancestors.items() if rid not in before_base}
            db.add(SyncConflict(conflict_id=str(uuid4()), project_id=tx['project_id'],
                                object_type=c['object_type'], object_id=c['object_id'], common_base=common,
                                head_set=hs, candidate_transactions=sorted(contenders), reason='SCIENTIFIC_DIVERGENCE',
                                status='open', resolution_revision=None, created_at=now, resolved_at=None))
            invalidated.update(contenders)
    db.flush()
    _fault(fault, 'after_conflict_create')
    if invalidated:
        invalidated = _invalidate(db, tx['project_id'], invalidated, transaction_id)
    if reviewed and not invalidated:
        for old_id in reviewed:
            db.get(SyncTransaction, old_id).state = 'SUPERSEDED'
        # Explicit full review is the new provenance; old descendants remain paused.
    blocked = any(db.get(SyncTransaction, dep).state != 'ACCEPTED'
                  for dep in dependencies if dep not in reviewed)
    closed_update = any(lifecycle != 'active' and c['operation'] == 'update'
                        for c, _, _, lifecycle in items)
    candidate = (transaction_id in invalidated or blocked or relationship_blocked or closed_update
                 or context.mode == 'offline_proposal')
    record.state = 'CANDIDATE' if candidate else 'ACCEPTED'
    if not candidate:
        for c, rev, doc, lifecycle in items:
            key = (tx['project_id'], c['object_type'], c['object_id'])
            db.execute(delete(AcceptedProjection).where(*_where(AcceptedProjection, key)))
            db.add(AcceptedProjection(project_id=tx['project_id'], object_type=c['object_type'], object_id=c['object_id'],
                                      revision=rev, transaction_id=transaction_id, document=doc, lifecycle=lifecycle))
    db.flush()
    _fault(fault, 'after_domain_projection')
    for c, rev, _, _ in items:
        append_audit(db, audit_id=c['audit_id'], project_id=tx['project_id'], transaction_id=transaction_id,
                     action='resolve_sync_conflict' if c['operation'] == 'resolve' else c['operation'],
                     content={'change': c, 'revision': rev})
    _fault(fault, 'after_audit_append')
    return _receipt(db, project, tx, envelope, context, record.state, fault, local_outbox, domain_action_digest)


def apply(engine, tx, context, *, fault=None, local_outbox=False):
    """Own a short atomic database transaction; retry transient DB races only."""
    for attempt in range(3):
        try:
            with Session(engine) as db, db.begin():
                return apply_in_session(db, tx, context, fault=fault, local_outbox=local_outbox)
        except (IntegrityError, OperationalError) as exc:
            code = getattr(getattr(exc, 'orig', None), 'sqlstate', None)
            if code in {'40001', '40P01'} and attempt < 2:
                continue
            if isinstance(exc, IntegrityError):
                raise ProtocolError('IDENTITY_COLLISION', 'database identity constraint rejected mutation') from exc
            raise

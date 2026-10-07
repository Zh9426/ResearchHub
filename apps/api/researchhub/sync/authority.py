"""Registered QA principals and server-issued mock consent. No authentication claim."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException

from ..service import scientific_authority
from .models import Grant, Principal
from .protocol import (
    ACTORS,
    ProtocolError,
    _uuid,
    transaction_digest,
    validate_transaction,
)


@dataclass(frozen=True)
class TrustedContext:
    principal_id: str
    grant_id: str | None = None
    mode: str = 'online'
    relay_seq: int | None = None


def register_principal(db, *, principal_id, user_id, device_id, session_id,
                       project_id, actor_id, actor_type):
    if actor_type not in ACTORS:
        raise ProtocolError('INVALID_PRINCIPAL', 'unknown registered actor')
    for value in (principal_id, user_id, device_id, session_id, project_id, actor_id):
        _uuid(value)
    principal = Principal(principal_id=principal_id, user_id=user_id, device_id=device_id,
                          session_id=session_id, project_id=project_id, actor_id=actor_id,
                          actor_type=actor_type, active=True)
    db.add(principal)
    db.flush()
    return principal


def principal_for(db, context, tx, *, replay=False):
    if not isinstance(context, TrustedContext) or context.mode not in {'online', 'offline_proposal'}:
        raise ProtocolError('INVALID_CONTEXT', 'registered trusted context required')
    principal = db.get(Principal, context.principal_id, populate_existing=True)
    if principal is None or not principal.active:
        raise ProtocolError('PRINCIPAL_REVOKED', 'principal is unregistered or revoked')
    for field in ('project_id', 'device_id', 'actor_id', 'actor_type'):
        if getattr(principal, field) != tx.get(field):
            raise ProtocolError('ACTOR_CONTEXT_MISMATCH', 'wire identity differs from registered principal')
    return principal


def resolve_principal(db, context, project_id):
    if not isinstance(context, TrustedContext):
        raise ProtocolError('INVALID_CONTEXT', 'trusted context required')
    row = db.get(Principal, context.principal_id, populate_existing=True)
    if row is None or not row.active or row.project_id != project_id:
        raise ProtocolError('PRINCIPAL_REVOKED', 'principal is unregistered, revoked or wrong project')
    return row


def grant_bindings(principal, tx):
    return {'user_id': principal.user_id, 'device_id': principal.device_id,
            'session_id': principal.session_id, 'project_id': principal.project_id,
            'objects': [{'object_type': c['object_type'], 'object_id': c['object_id'],
                         'operation': c['operation'], 'expected_heads': c['parents']}
                        for c in tx['changes']]}


def issue_grant(db, context, tx, *, expires_at=None):
    validate_transaction(tx)
    principal = principal_for(db, context, tx)
    if principal.actor_type != 'human' or context.mode != 'online':
        raise ProtocolError('HUMAN_REQUIRED', 'only online registered Human can consent')
    now = datetime.now(timezone.utc)
    expiry = expires_at or now + timedelta(minutes=5)
    if (not isinstance(expiry, datetime) or expiry.tzinfo is None
            or not now < expiry <= now + timedelta(minutes=5)):
        raise ProtocolError('GRANT_INVALID', 'fresh consent expires within five minutes')
    grant = Grant(grant_id=str(uuid4()), principal_id=principal.principal_id,
                  bindings=grant_bindings(principal, tx), transaction_id=tx['transaction_id'],
                  digest=transaction_digest(tx),
                  expires_at=expiry,
                  consumed=False)
    db.add(grant)
    db.flush()
    return grant.grant_id


def protected(kind, document):
    return (
        (kind == 'ResearchRun' and bool(document.get('human_conclusion')))
        or (kind == 'HumanConclusion' and document.get('status') == 'final')
        or (kind in {'Parameter', 'Metric'} and document.get('is_confirmed') is True)
        or (kind in {'Evidence', 'Metric', 'Parameter'} and document.get('status') in {'validated', 'reproduced'})
        or (kind in {'Gate', 'GateCriterion'} and document.get('status') == 'passed')
        or (kind == 'Gate' and any(c.get('status') == 'passed' for c in document.get('criteria', [])))
        or (kind == 'Decision' and document.get('status') == 'accepted')
        or (kind == 'Claim' and document.get('status') == 'supported')
        or kind == 'ModuleUpgrade'
    )


def assert_domain_ai_scope(principal, change, parents):
    """Reuse v0.2 checks after reconstructing actor from registered identity."""
    if principal.actor_type == 'human':
        return
    actor = SimpleNamespace(token=True, actor_type=principal.actor_type)
    kind = {'ResearchRun': 'runs', 'Parameter': 'parameters', 'Metric': 'metrics',
            'Evidence': 'evidence', 'Decision': 'decisions', 'Gate': 'gates',
            'Claim': 'claims'}.get(change['object_type'])
    if kind is None:
        return
    old_documents = [parent.document for parent in parents] or [None]
    for document in old_documents:
        old = (SimpleNamespace(is_confirmed=document.get('is_confirmed', False),
                               status=document.get('status', 'proposed'))
               if document is not None else None)
        try:
            scientific_authority(actor, kind, change['payload'], existing=old,
                                 creating=change['operation'] == 'create')
        except HTTPException as exc:
            raise ProtocolError('HUMAN_REQUIRED', 'Human-only existing Domain authority') from exc


def consume_grant(db, context, principal, tx):
    if principal.actor_type != 'human' or context.mode != 'online':
        raise ProtocolError('HUMAN_REQUIRED', 'final authority requires fresh online Human consent')
    grant = db.get(Grant, context.grant_id, populate_existing=True) if context.grant_id else None
    if (grant is None or grant.consumed or grant.principal_id != principal.principal_id
            or grant.transaction_id != tx['transaction_id'] or grant.digest != transaction_digest(tx)
            or grant.bindings != grant_bindings(principal, tx)
            or grant.expires_at <= datetime.now(timezone.utc)):
        raise ProtocolError('GRANT_REQUIRED', 'fresh exact scoped consent is required')
    grant.consumed = True
    db.flush()

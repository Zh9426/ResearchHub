"""QA-only SQLAlchemy metadata. No product Base or automatic migration."""

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class KernelBase(DeclarativeBase):
    pass


SyncKernelBase = KernelBase


class ProjectState(KernelBase):
    __tablename__ = 'sync_kernel_projects'
    project_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    module_snapshot_hash: Mapped[str] = mapped_column(String(64))
    received_cursor: Mapped[int] = mapped_column(Integer, default=0)
    accepted_watermark: Mapped[int] = mapped_column(Integer, default=0)


class Principal(KernelBase):
    __tablename__ = 'sync_kernel_principals'
    principal_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36))
    device_id: Mapped[str] = mapped_column(String(36))
    session_id: Mapped[str] = mapped_column(String(36))
    project_id: Mapped[str] = mapped_column(ForeignKey(ProjectState.project_id))
    actor_id: Mapped[str] = mapped_column(String(36))
    actor_type: Mapped[str] = mapped_column(String(16))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Grant(KernelBase):
    __tablename__ = 'sync_kernel_grants'
    grant_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    principal_id: Mapped[str] = mapped_column(ForeignKey(Principal.principal_id))
    bindings: Mapped[dict] = mapped_column(JSONB)
    transaction_id: Mapped[str] = mapped_column(String(36), unique=True)
    digest: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[object] = mapped_column(DateTime(timezone=True))
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)


class SyncTransaction(KernelBase):
    __tablename__ = 'sync_kernel_transactions'
    transaction_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(36), unique=True)
    project_id: Mapped[str] = mapped_column(ForeignKey(ProjectState.project_id), index=True)
    digest: Mapped[str] = mapped_column(String(64), unique=True)
    state: Mapped[str] = mapped_column(String(24), index=True)
    raw: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[str] = mapped_column(String(24))


class ObjectRevision(KernelBase):
    __tablename__ = 'sync_kernel_revisions'
    revision: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey(ProjectState.project_id), index=True)
    object_type: Mapped[str] = mapped_column(String(32))
    object_id: Mapped[str] = mapped_column(String(36))
    transaction_id: Mapped[str] = mapped_column(ForeignKey(SyncTransaction.transaction_id), index=True)
    change_id: Mapped[str] = mapped_column(String(36), unique=True)
    parents: Mapped[list] = mapped_column(JSONB)
    semantic: Mapped[dict] = mapped_column(JSONB)
    document: Mapped[dict] = mapped_column(JSONB)
    lifecycle: Mapped[str] = mapped_column(String(16))
    __table_args__ = (UniqueConstraint('revision', 'project_id', 'object_type', 'object_id'),)


class RevisionParent(KernelBase):
    __tablename__ = 'sync_kernel_revision_parents'
    revision: Mapped[str] = mapped_column(String(64), primary_key=True)
    parent: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36))
    object_type: Mapped[str] = mapped_column(String(32))
    object_id: Mapped[str] = mapped_column(String(36))
    __table_args__ = (
        ForeignKeyConstraint(['revision', 'project_id', 'object_type', 'object_id'],
                             ['sync_kernel_revisions.revision', 'sync_kernel_revisions.project_id',
                              'sync_kernel_revisions.object_type', 'sync_kernel_revisions.object_id']),
        ForeignKeyConstraint(['parent', 'project_id', 'object_type', 'object_id'],
                             ['sync_kernel_revisions.revision', 'sync_kernel_revisions.project_id',
                              'sync_kernel_revisions.object_type', 'sync_kernel_revisions.object_id']),
    )


class ObjectHead(KernelBase):
    __tablename__ = 'sync_kernel_heads'
    project_id: Mapped[str] = mapped_column(ForeignKey(ProjectState.project_id), primary_key=True)
    object_type: Mapped[str] = mapped_column(String(32), primary_key=True)
    object_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    revision: Mapped[str] = mapped_column(ForeignKey(ObjectRevision.revision), primary_key=True)


class TransactionMember(KernelBase):
    __tablename__ = 'sync_kernel_members'
    transaction_id: Mapped[str] = mapped_column(ForeignKey(SyncTransaction.transaction_id), primary_key=True)
    revision: Mapped[str] = mapped_column(ForeignKey(ObjectRevision.revision), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    object_type: Mapped[str] = mapped_column(String(32))
    object_id: Mapped[str] = mapped_column(String(36))
    ordinal: Mapped[int] = mapped_column(Integer)


class Dependency(KernelBase):
    __tablename__ = 'sync_kernel_dependencies'
    transaction_id: Mapped[str] = mapped_column(ForeignKey(SyncTransaction.transaction_id), primary_key=True)
    depends_on: Mapped[str] = mapped_column(ForeignKey(SyncTransaction.transaction_id), primary_key=True, index=True)
    project_id: Mapped[str] = mapped_column(String(36), index=True)


class AcceptedProjection(KernelBase):
    __tablename__ = 'sync_kernel_projections'
    project_id: Mapped[str] = mapped_column(ForeignKey(ProjectState.project_id), primary_key=True)
    object_type: Mapped[str] = mapped_column(String(32), primary_key=True)
    object_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    revision: Mapped[str] = mapped_column(ForeignKey(ObjectRevision.revision))
    transaction_id: Mapped[str] = mapped_column(ForeignKey(SyncTransaction.transaction_id), index=True)
    document: Mapped[dict] = mapped_column(JSONB)
    lifecycle: Mapped[str] = mapped_column(String(16))


class SyncConflict(KernelBase):
    __tablename__ = 'sync_kernel_conflicts'
    conflict_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey(ProjectState.project_id), index=True)
    object_type: Mapped[str] = mapped_column(String(32))
    object_id: Mapped[str] = mapped_column(String(36))
    common_base: Mapped[str | None] = mapped_column(ForeignKey(ObjectRevision.revision), nullable=True)
    head_set: Mapped[list] = mapped_column(JSONB)
    candidate_transactions: Mapped[list] = mapped_column(JSONB)
    reason: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), index=True)
    resolution_revision: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Audit(KernelBase):
    __tablename__ = 'sync_kernel_audits'
    audit_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey(ProjectState.project_id), index=True)
    transaction_id: Mapped[str] = mapped_column(ForeignKey(SyncTransaction.transaction_id), index=True)
    action: Mapped[str] = mapped_column(String(48))
    content: Mapped[dict] = mapped_column(JSONB)
    digest: Mapped[str] = mapped_column(String(64))


class Inbox(KernelBase):
    __tablename__ = 'sync_kernel_inbox'
    transaction_id: Mapped[str] = mapped_column(ForeignKey(SyncTransaction.transaction_id), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey(ProjectState.project_id))
    sequence: Mapped[int] = mapped_column(Integer)
    digest: Mapped[str] = mapped_column(String(64))
    receipt: Mapped[dict] = mapped_column(JSONB)
    __table_args__ = (UniqueConstraint('project_id', 'sequence'),)


class Outbox(KernelBase):
    __tablename__ = 'sync_kernel_outbox'
    transaction_id: Mapped[str] = mapped_column(ForeignKey(SyncTransaction.transaction_id), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey(ProjectState.project_id))
    digest: Mapped[str] = mapped_column(String(64))
    action_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    envelope: Mapped[dict] = mapped_column(JSONB)
    state: Mapped[str] = mapped_column(String(24), default='LOCAL_COMMITTED')


class VerifiedArtifact(KernelBase):
    __tablename__ = 'sync_kernel_verified_artifacts'
    project_id: Mapped[str] = mapped_column(ForeignKey(ProjectState.project_id), primary_key=True)
    key_epoch: Mapped[int] = mapped_column(Integer, primary_key=True)
    checksum: Mapped[str] = mapped_column(String(64), primary_key=True)
    size: Mapped[int] = mapped_column(Integer, primary_key=True)


def initialize_qa(engine):
    """Explicit setup, only after verifying the dedicated QA connection identity."""
    from .qa import QA_DATABASE, QA_USER, assert_qa_bind
    assert_qa_bind(engine)
    if engine.dialect.name != 'postgresql':
        raise RuntimeError('Kernel requires PostgreSQL, never SQLite')
    with engine.begin() as connection:
        identity = connection.execute(text('SELECT current_database(), current_user')).one()
        if tuple(identity) != (QA_DATABASE, QA_USER):
            raise RuntimeError('Only dedicated QA metadata initialization is allowed')
        KernelBase.metadata.create_all(connection)
        # Additive QA setup only; this is never a production migration.
        connection.execute(text('ALTER TABLE sync_kernel_outbox ADD COLUMN IF NOT EXISTS action_digest varchar(64)'))
        connection.execute(text('''CREATE OR REPLACE FUNCTION sync_kernel_immutable()
            RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
            RAISE EXCEPTION 'immutable sync history cannot be modified'; END $$'''))
        for table in ('sync_kernel_revisions', 'sync_kernel_revision_parents',
                      'sync_kernel_members', 'sync_kernel_dependencies', 'sync_kernel_audits',
                      'sync_kernel_inbox', 'sync_kernel_outbox'):
            connection.execute(text(f'DROP TRIGGER IF EXISTS immutable ON {table}'))
            connection.execute(text(f'CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON {table} '
                                    'FOR EACH ROW EXECUTE FUNCTION sync_kernel_immutable()'))
        connection.execute(text('''CREATE OR REPLACE FUNCTION sync_kernel_parent_declared()
            RETURNS trigger LANGUAGE plpgsql AS $$ DECLARE declared jsonb; BEGIN
            SELECT parents INTO declared FROM sync_kernel_revisions WHERE revision=NEW.revision;
            IF NEW.parent=NEW.revision OR NOT (declared ? NEW.parent) THEN
              RAISE EXCEPTION 'immutable parent declaration mismatch or cycle';
            END IF;
            RETURN NEW; END $$'''))
        connection.execute(text('DROP TRIGGER IF EXISTS declared_parent ON sync_kernel_revision_parents'))
        connection.execute(text('CREATE TRIGGER declared_parent BEFORE INSERT ON sync_kernel_revision_parents '
                                'FOR EACH ROW EXECUTE FUNCTION sync_kernel_parent_declared()'))
        connection.execute(text('DROP TRIGGER IF EXISTS immutable_identity ON sync_kernel_transactions'))
        connection.execute(text('CREATE TRIGGER immutable_identity BEFORE UPDATE OF transaction_id, '
                                'idempotency_key, project_id, digest, raw, created_at ON sync_kernel_transactions '
                                'FOR EACH ROW EXECUTE FUNCTION sync_kernel_immutable()'))

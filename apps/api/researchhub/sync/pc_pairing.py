"""SYNTHETIC owner pairing: durable public journal, exact SQLite receipts, QA PG.

Lock order: project advisory -> PG Kernel/Trust -> SQLite. Network failures are
observable UNKNOWN states, never an implicit retry or a reason to mint a grant.
"""
import hashlib
import json
import time
from contextlib import contextmanager
from uuid import uuid4

import httpx
from sqlalchemy import String, Integer, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column
from packages.secure_wire.canonical import canonical_bytes, digest, strict_loads
from packages.secure_wire.membership import validate_member, verify_transition, verify_grant
from .authority import register_principal
from .kernel import lock_project
from .models import SyncTransaction, Principal
from .pc_records import PcBase
from .secure import pairing, transport_pg
from .secure.keys import TrustedStore


def make_transport(engine,node):
    """Use the existing run's local CA file; never install a CA or disable TLS."""
    import json
    from pathlib import Path
    from .secure.transport import SecureTransport
    root=Path(__file__).resolve().parents[4]
    state=json.loads((root/'storage/runtime/secure-relay-run.json').read_text(encoding='utf-8'))
    if state.get('scope')!='secure-relay-s2' or state.get('phase')!='ready':
        raise ValueError('RELAY_QA_SETUP_REQUIRED')
    ca=Path(state['tls_directory']).resolve()/'ca.crt'
    if not ca.is_relative_to((root/'storage/runtime').resolve()):raise ValueError('QA_CA_PATH_REQUIRED')
    return SecureTransport(engine,node.binding['opaque_project_id'],node.owner,str(ca),{})


def pin_node_bootstrap(node):
    """Explicit QA admin setup, public bootstrap only; never an HTTP auto-pin."""
    import os
    import json
    import sys
    from pathlib import Path
    from sqlalchemy.engine import URL
    if os.environ.get('HUB_SYNC_QA')!='1' or os.environ.get('HUB_RELAY_QA')!='1':
        raise ValueError('EXPLICIT_QA_SETUP_REQUIRED')
    root=Path(__file__).resolve().parents[4]
    sys.path.insert(0,str(root/'apps/relay'))
    from researchhub_relay.qa import connect
    from researchhub_relay.service import pin_bootstrap
    config=json.loads((root/'storage/runtime/secure-relay-qa.json').read_text(encoding='utf-8'))
    if config.get('scope')!='secure-relay-s2':raise ValueError('RELAY_QA_CONFIG_REQUIRED')
    url=URL.create('postgresql+psycopg',username=config['username'],password=config['password'],
        host=config['host'],port=config['port'],database=config['database'])
    engine=connect(url.render_as_string(hide_password=False),profile='host')
    try:
        trust=node.binding['trust']
        if len(trust['manifest_chain'])!=1:raise ValueError('BOOTSTRAP_ONLY')
        pin_bootstrap(engine,trust['manifest_chain'][0],trust['owner_root'],trust['recovery_root'])
    finally:engine.dispose()


class PairingJournal(PcBase):
    __tablename__='qa_pc_pairing_journal'
    session_id: Mapped[str]=mapped_column(String(36),primary_key=True)
    project: Mapped[str]=mapped_column(String(36),index=True)
    active_project: Mapped[str | None]=mapped_column(String(36),unique=True,nullable=True)
    stage: Mapped[str]=mapped_column(String(24))
    reserved: Mapped[dict]=mapped_column(JSONB)
    challenge: Mapped[dict | None]=mapped_column(JSONB,nullable=True)
    receipt: Mapped[dict | None]=mapped_column(JSONB,nullable=True)
    result: Mapped[dict | None]=mapped_column(JSONB,nullable=True)


class BindingHead(PcBase):
    __tablename__='qa_pc_binding_heads'
    project: Mapped[str]=mapped_column(String(36),primary_key=True)
    head: Mapped[str]=mapped_column(String(64),primary_key=True)
    principal_map: Mapped[dict]=mapped_column(JSONB)


class RelayOldHead(Exception):
    """Only a verified authorization rejection permits the old-head query."""


@contextmanager
def project_lock(engine,project):
    transport_pg.guard(engine)
    key=int(hashlib.sha256(('pc-pairing:'+project).encode()).hexdigest()[:15],16)
    with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
        connection.execute(text('SELECT pg_advisory_lock(:key)'),{'key':key})
        try:yield
        finally:connection.execute(text('SELECT pg_advisory_unlock(:key)'),{'key':key})


def active_journal(db,project):
    return db.scalar(select(PairingJournal).where(PairingJournal.active_project==project))


def fixed_public_map(db,trust,manifest):
    principals=strict_loads(trust.principals)
    result=[]
    for member in manifest['members']:
        if member['status']!='ACTIVE':continue
        row=db.get(Principal,principals.get(member['device_id']))
        if row is None or not row.active or row.device_id!=member['device_id'] or row.project_id!=trust.semantic_project:
            raise ValueError('BLOCKED_PRINCIPAL_MAP')
        result.append(dict(device_id=row.device_id,actor_id=row.actor_id,actor_type=row.actor_type,role=member['role']))
    result.sort(key=lambda item:item['device_id'])
    key=(trust.project,digest(manifest));saved=db.get(BindingHead,key)
    if saved is None:
        db.add(BindingHead(project=key[0],head=key[1],principal_map=result));db.flush()
    elif saved.principal_map!=result:
        raise ValueError('BLOCKED_PRINCIPAL_MAP_CHANGED')
    return result


class OwnerPairing:
    def __init__(self,engine,node,transport):
        transport_pg.guard(engine)
        self.engine,self.node,self.transport=engine,node,transport
        self.project=node.binding['opaque_project_id']
        self.semantic=node.binding['semantic_project_id']
        self.store=TrustedStore(node.runtime/'trust.sqlite')

    def _locked(self,db):
        lock_project(db,self.semantic)
        return transport_pg.locked(db,self.project)

    def _row(self,db,session):
        row=db.get(PairingJournal,session)
        if row is None or row.project!=self.project:raise ValueError('PAIRING_SESSION_MISMATCH')
        return row

    def _empty(self,db,trust):
        if trust.cursor or db.scalar(select(SyncTransaction.transaction_id).where(SyncTransaction.project_id==self.semantic).limit(1)):
            raise ValueError('EMPTY_PROJECT_REQUIRED')

    def _view(self,row):
        if row.stage=='COMPLETE':
            # JSONB and canonical decoding reorder keys. The source 3A hash is
            # specifically JSON.stringify, so recover its already-frozen order
            # while retaining the exact historical wrapper and signed bytes.
            original=canonical_bytes(row.result)
            result=strict_loads(original)
            binding=result['signed_binding']['binding']
            snapshot=self.node.binding['module_snapshot']
            serialized=json.dumps(snapshot,ensure_ascii=False,separators=(',',':'))
            if (canonical_bytes(binding['module_snapshot'])!=canonical_bytes(snapshot)
                    or binding['module_snapshot_hash']!=digest(snapshot)
                    or binding['local_module_hash']!={'algorithm':'sha256-json-stringify',
                        'value':hashlib.sha256(serialized.encode()).hexdigest()}):
                raise ValueError('BLOCKED_FROZEN_SNAPSHOT_MISMATCH')
            binding['module_snapshot']=strict_loads(serialized)
            if canonical_bytes(result)!=original:raise ValueError('BLOCKED_SIGNED_RESPONSE_CHANGED')
            return result
        value={'session_id':row.session_id,'stage':row.stage,'expires_at':row.reserved['issued_at']+300}
        if row.challenge is not None:
            value.update(challenge=row.challenge,confirmation=pairing.confirmation(row.challenge))
        # Public roots/chain are conveyed explicitly for human trust confirmation.
        value['bootstrap']=row.reserved['bootstrap']
        return value

    def status(self,session_id=None):
        with Session(self.engine) as db,db.begin():
            trust,history=self._locked(db)
            row=self._row(db,session_id) if session_id else active_journal(db,self.project)
            if row is not None and row.stage=='COMPLETE':self._completed(row,history)
            return self._view(row) if row else {'stage':'IDLE'}

    def _completed(self,row,history):
        # A historical grant is not a present authorization after revoke/rotation.
        receipt=pairing.retry_receipt(self.store,row.challenge,row.reserved['recipient']['device_id'])
        if (receipt!=row.receipt or digest(history[-1])!=digest(receipt['manifest'])
                or digest(self.store.verified_current(self.project))!=digest(history[-1])):
            raise ValueError('BLOCKED_COMPLETED_PAIRING_STALE')

    def start(self,recipient,*,now=None,fault=None):
        now=int(time.time()) if now is None else now
        validate_member(recipient)
        if recipient['role']!='writer' or recipient['status']!='ACTIVE':raise ValueError('WRITER_RECIPIENT_REQUIRED')
        with project_lock(self.engine,self.project):
            with Session(self.engine) as db,db.begin():
                trust,history=self._locked(db)
                if active_journal(db,self.project):raise ValueError('ACTIVE_PAIRING_REQUIRED_RESUME')
                self._empty(db,trust)
                old=history[-1]
                if digest(self.store.verified_current(self.project))!=digest(old):raise ValueError('BLOCKED_PIN_MISMATCH')
                if any(m['device_id']==recipient['device_id'] for m in old['members']):raise ValueError('DEVICE_ALREADY_REGISTERED')
                fixed_public_map(db,trust,old)
                # Current-trust request uses a separate PG session; release row locks first.
            hello=self.transport.request('POST','/v1/hello',{})
            if hello.get('sequence')!=0:raise ValueError('EMPTY_RELAY_REQUIRED')
            if hello.get('manifest_digest')!=digest(old):raise ValueError('BLOCKED_RELAY_HEAD')
            with Session(self.engine) as db,db.begin():
                trust,history=self._locked(db);self._empty(db,trust)
                if digest(history[-1])!=digest(old):raise ValueError('BLOCKED_PIN_MISMATCH')
                sid=str(uuid4())
                # Owner allocates the prefix; pasted input cannot choose it.
                recipient={**recipient,'nonce_prefix':max(m['nonce_prefix'] for m in old['members'])+1}
                validate_member(recipient)
                reserved={'old':old,'recipient':recipient,'issued_at':now,'principal_id':str(uuid4()),
                    'actor_id':str(uuid4()),'principal_session':str(uuid4()),
                    'bootstrap':{'owner_root':trust.owner,'recovery_root':trust.recovery,'manifest_chain':history}}
                db.add(PairingJournal(session_id=sid,project=self.project,active_project=self.project,
                    stage='RESERVED',reserved=reserved))
                if fault:fault('before_reserved_commit')
            if fault:fault('after_reserved')
            return self._resume(sid,now=now,fault=fault)

    def resume(self,session_id,*,now=None,fault=None):
        with project_lock(self.engine,self.project):
            return self._resume(session_id,now=int(time.time()) if now is None else now,fault=fault)

    def confirm(self,session_id,proof,*,now=None,fault=None):
        with project_lock(self.engine,self.project):
            return self._resume(session_id,proof=proof,now=int(time.time()) if now is None else now,fault=fault)

    def _resume(self,session_id,*,now,proof=None,fault=None):
        with Session(self.engine) as db,db.begin():
            trust,history=self._locked(db);row=self._row(db,session_id)
            if row.stage=='COMPLETE':
                self._completed(row,history)
                return self._view(row)
            if row.stage in ('EXPIRED','BLOCKED'):return self._view(row)
            r=row.reserved;old=r['old']
            if digest(history[-1])!=digest(old):raise ValueError('BLOCKED_JOURNAL_HEAD')
            self._empty(db,trust)
            try:
                challenge=pairing.create_or_load_reserved_challenge(self.store,self.node.owner,r['recipient'],
                    session_id=session_id,project=self.project,expected_manifest_digest=digest(old),
                    issued_at=r['issued_at'],now=now)
                if fault:fault('after_challenge_create')
            except ValueError as exc:
                if str(exc)!='PAIRING_EXPIRED':raise
                row.stage='EXPIRED';row.active_project=None
                return self._view(row)
            if row.challenge is not None and row.challenge!=challenge:raise ValueError('BLOCKED_CHALLENGE_MISMATCH')
            row.challenge=challenge
            with self.store.transaction() as sqlite:
                used=sqlite.execute('SELECT used FROM challenges WHERE session=?',(session_id,)).fetchone()[0]
            if used:
                receipt=pairing.retry_receipt(self.store,challenge,r['recipient']['device_id'])
                if row.receipt is not None and row.receipt!=receipt:raise ValueError('BLOCKED_RECEIPT_MISMATCH')
                row.receipt=receipt;row.stage='CONSUMED'
            elif now>=challenge['expires_at']:
                row.stage='EXPIRED';row.active_project=None
            else:row.stage='CHALLENGE_READY'
            view=self._view(row)
        if fault:fault('after_challenge')
        if view['stage']=='EXPIRED':return view
        if not used:
            if proof is None:return view
            with Session(self.engine) as db,db.begin():
                self._locked(db);row=self._row(db,session_id)
                receipt=pairing.consume(self.store,self.node.owner,challenge,proof,self.node.project_key,now=now)
                if fault:fault('after_consume')
                row.receipt=receipt;row.stage='CONSUMED'
        with Session(self.engine) as db,db.begin():
            trust,history=self._locked(db);row=self._row(db,session_id)
            candidate=row.receipt['manifest'];verify_transition(old,candidate,trust.recovery)
            verify_grant(row.receipt['grant'],candidate)
            if (row.receipt['challenge_digest']!=digest(challenge)
                    or row.receipt['grant']['context']['session_id']!=session_id
                    or row.receipt['grant']['context']['recipient_device_id']!=r['recipient']['device_id']
                    or candidate['key_epoch']!=old['key_epoch']
                    or candidate['members']!=[*old['members'],r['recipient']]
                    or digest(self.store.verified_current(self.project))!=digest(candidate)):
                raise ValueError('BLOCKED_RECEIPT_SCOPE')
            # Always resolve a possible previous ACK before considering an exact resend.
            try:
                try:ack=self.transport.pairing_request(session_id,'receipt',db=db)
                except RelayOldHead:
                    current=self.transport.pairing_request(session_id,'current',db=db)
                    if digest(current)!=digest(old):
                        row.stage='BLOCKED';return self._view(row)
                    ack=self.transport.pairing_request(session_id,'publish',db=db)
            except (httpx.TransportError,OSError):
                row.stage='RELAY_UNKNOWN';return self._view(row)
            except httpx.HTTPStatusError as exc:
                row.stage='RELAY_UNKNOWN' if exc.response.status_code>=500 or exc.response.status_code in (408,429) else 'BLOCKED'
                return self._view(row)
            except ValueError as exc:
                row.stage='RELAY_UNKNOWN' if str(exc)=='RESPONSE_TIMEOUT' else 'BLOCKED'
                return self._view(row)
            except RelayOldHead:
                row.stage='BLOCKED';return self._view(row)
            if ack!={'manifest_digest':digest(candidate),'membership_epoch':candidate['membership_epoch'],'key_epoch':candidate['key_epoch']}:
                row.stage='BLOCKED';return self._view(row)
            row.stage='RELAY_CONFIRMED'
        # Relay acknowledgement has its own durable stage before the PG CAS.
        with Session(self.engine) as db,db.begin():
            trust,history=self._locked(db);row=self._row(db,session_id)
            if digest(history[-1])!=digest(old):raise ValueError('BLOCKED_JOURNAL_HEAD')
            self._empty(db,trust)
            principals=strict_loads(trust.principals)
            if r['recipient']['device_id'] in principals:raise ValueError('BLOCKED_PRINCIPAL_COLLISION')
            owner_principal=db.get(Principal,self.node.context.principal_id)
            register_principal(db,principal_id=r['principal_id'],user_id=owner_principal.user_id,
                device_id=r['recipient']['device_id'],session_id=r['principal_session'],project_id=self.semantic,
                actor_id=r['actor_id'],actor_type='human')
            principals[r['recipient']['device_id']]=r['principal_id']
            trust.history=canonical_bytes([*history,candidate]);trust.principals=canonical_bytes(principals)
            fixed_public_map(db,trust,candidate)
            from .pc_identity import binding_in_session
            binding,wrapper=binding_in_session(db,self.node.owner,self.node.runtime,r['recipient']['device_id'])
            row.result={'session_id':session_id,'stage':'COMPLETE','pairing_receipt':row.receipt,'signed_binding':wrapper}
            row.stage='COMPLETE';row.active_project=None
            result=self._view(row)
            if fault:fault('before_pg_commit')
        return result

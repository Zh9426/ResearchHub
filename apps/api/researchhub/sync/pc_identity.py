"""Owned, resumable SYNTHETIC QA setup; UNPROTECTED device files, never product use."""
import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass, field
from contextlib import closing
from pathlib import Path
from uuid import uuid4

from sqlalchemy import String, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column
from packages.secure_wire.canonical import canonical_bytes, digest, strict_loads
from packages.secure_wire.membership import member_of
from .. import models as domain
from ..modules import load_modules
from .authority import TrustedContext, register_principal
from .kernel import register_project
from .pc_records import PcBase
from .secure import transport_pg
from .secure.keys import TestOnlyFileDeviceKeyStore, TrustedStore, bootstrap, make_grant, open_grant, signed_object
from .secure.nonce import NonceVault

class PcNode(PcBase):
    __tablename__='qa_pc_nodes'
    node_id: Mapped[str]=mapped_column(String(64),primary_key=True)
    stage: Mapped[str]=mapped_column(String(16))
    metadata_public: Mapped[dict]=mapped_column(JSONB)

@dataclass
class Node:
    binding: dict
    signed_binding: dict
    context: TrustedContext
    owner: object=field(repr=False)
    project_key: bytes=field(repr=False)
    runtime: Path

def setup_node(engine,runtime,module_id='generic'):
    if os.environ.get('HUB_SYNC_QA')!='1':raise RuntimeError('Explicit HUB_SYNC_QA=1 required')
    transport_pg.guard(engine)
    runtime=Path(runtime).resolve()
    root=Path(__file__).resolve().parents[4]/'storage/runtime/browser-sync-qa/pc'
    if not runtime.is_relative_to(root.resolve()):raise ValueError('PC_OWNED_RUNTIME_REQUIRED')
    if module_id not in ('generic','hdsp','ice-sonocuring'):raise ValueError('QA_MODULE_REQUIRED')
    transport_pg.initialize(engine)
    with engine.begin() as connection:
        domain.Base.metadata.create_all(connection)
        PcBase.metadata.create_all(connection)
    runtime.mkdir(parents=True,exist_ok=True)
    node_id=hashlib.sha256(str(runtime).encode()).hexdigest()
    # Database advisory lock covers setup across workers and restarts. No file lock takeover.
    with Session(engine) as db, db.begin():
        db.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':int(node_id[:15],16)})
        row=db.get(PcNode,node_id)
        existing=row is not None
        for name in ('owner.sqlite','recovery.sqlite'):
            if existing and not (runtime/name).is_file():raise ValueError('BLOCKED_MISSING_DEVICE')
            if existing:
                try:
                    with closing(sqlite3.connect(f'file:{(runtime/name).as_posix()}?mode=ro',uri=True)) as keys:
                        saved=keys.execute('SELECT id,signing,recipient FROM qa_device WHERE singleton=1').fetchone()
                        if saved is None or len(saved[1])!=32 or len(saved[2])!=32:raise ValueError('BLOCKED_MISSING_DEVICE')
                except sqlite3.DatabaseError:raise ValueError('BLOCKED_MISSING_DEVICE') from None
        owner=TestOnlyFileDeviceKeyStore(runtime/'owner.sqlite').load_or_create()
        recovery=TestOnlyFileDeviceKeyStore(runtime/'recovery.sqlite').load_or_create()
        nonce=NonceVault(runtime/'nonce.sqlite')
        if existing:
            meta=row.metadata_public
            if meta['module_id']!=module_id:raise ValueError('MODULE_FROZEN')
            if not all(p.is_file() for p in (nonce.path,nonce.witness_path,nonce.anchor_path)):
                raise ValueError('BLOCKED_NONCE_STATE_MISSING')
        else:
            semantic=str(uuid4()); opaque=str(uuid4()); principal=str(uuid4()); user=str(uuid4())
            manifest=bootstrap(opaque,owner,recovery)
            key=os.urandom(32)
            grant=make_grant(manifest,owner,owner.device_id,str(uuid4()),key)
            nonce.register_new(key,0)
            snapshot=strict_loads(canonical_bytes(load_modules()[module_id]))
            # Freeze JS-compatible key order explicitly; PostgreSQL JSONB otherwise reorders it.
            snapshot_json=json.dumps(snapshot,ensure_ascii=False,separators=(',',':'))
            meta={'semantic':semantic,'opaque':opaque,'principal':principal,'user':user,
                  'actor':str(uuid4()),'session':str(uuid4()),'module_id':module_id,
                  'snapshot_json':snapshot_json,'manifest':manifest,'grant':grant,
                  'owner_root':owner.signing_public,'recovery_root':recovery.signing_public}
            row=PcNode(node_id=node_id,stage='PREPARED',metadata_public=meta)
            db.add(row);db.flush()
        stage=row.stage
    # PREPARED is durable before cross-store pinning; every remaining step is idempotent.
    store_path=runtime/'trust.sqlite'
    if stage=='READY' and not store_path.is_file():raise ValueError('BLOCKED_TRUST_STATE_MISSING')
    store=TrustedStore(store_path)
    try:
        current=store.verified_current(meta['opaque'])
    except ValueError as exc:
        if stage!='PREPARED' or str(exc)!='UNTRUSTED_PROJECT':raise
        store.bootstrap(meta['manifest'],meta['owner_root'],meta['recovery_root'])
        current=store.verified_current(meta['opaque'])
    with Session(engine) as db, db.begin():
        db.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':int(node_id[:15],16)})
        row=db.get(PcNode,node_id)
        trust=db.get(transport_pg.Trust,meta['opaque'])
        snapshot=json.loads(meta['snapshot_json'])
        public_principal={'device_id':owner.device_id,'actor_id':meta['actor'],'actor_type':'human','role':'owner'}
        if trust is None:
            if row.stage!='PREPARED':raise ValueError('BLOCKED_TRUST_PIN_MISSING')
            trust=transport_pg.Trust(project=meta['opaque'],semantic_project=meta['semantic'],
                owner=meta['owner_root'],recovery=meta['recovery_root'],history=canonical_bytes([meta['manifest']]),
                principals=canonical_bytes({owner.device_id:meta['principal']}))
            db.add(trust);db.flush()
        trust,chain=transport_pg.locked(db,meta['opaque'])
        if (trust.owner!=meta['owner_root'] or trust.recovery!=meta['recovery_root']
                or trust.semantic_project!=meta['semantic'] or digest(chain[-1])!=digest(current)):
            raise ValueError('BLOCKED_PIN_MISMATCH')
        target=member_of(current,owner.device_id,roles=('owner',))
        if target['signing_public_key']!=owner.signing_public or target['recipient_public_key']!=owner.recipient_public:
            raise ValueError('BLOCKED_DEVICE_KEY_MISMATCH')
        if (recovery.signing_public!=meta['recovery_root']
                or recovery.recipient_public!=current['recovery_recipient_public_key']
                or recovery.device_id!=current['recovery_device_id']):raise ValueError('BLOCKED_RECOVERY_KEY_MISMATCH')
        grant=meta['grant']; historical=store.history(meta['opaque'],grant['context']['membership_epoch'])
        if grant['manifest_digest']!=digest(historical) or grant['context']['key_epoch']!=current['key_epoch']:
            raise ValueError('BLOCKED_SELF_GRANT_EPOCH')
        key=open_grant(grant,historical,owner)
        # Validate, consuming a harmless counter on each restart; a missing/corrupt ledger never resets.
        nonce.reserve(key,target['nonce_prefix'])
        if row.stage=='PREPARED':
            if db.get(domain.User,meta['user']) is None:
                db.add(domain.User(id=meta['user'],email=meta['user']+'@example.invalid',
                    display_name='SYNTHETIC PC QA',password_hash='SYNTHETIC-NO-LOGIN'));db.flush()
                db.add(domain.Project(id=meta['semantic'],owner_id=meta['user'],name='SYNTHETIC PC '+module_id,
                    module_id=module_id,module_version=snapshot['version'],module_snapshot=snapshot));db.flush()
                register_project(db,meta['semantic'],digest(snapshot))
                register_principal(db,principal_id=meta['principal'],user_id=meta['user'],device_id=owner.device_id,
                    session_id=meta['session'],project_id=meta['semantic'],actor_id=meta['actor'],actor_type='human')
            row.stage='READY'
        binding={'binding_version':1,'semantic_project_id':meta['semantic'],'opaque_project_id':meta['opaque'],
            'module_snapshot':snapshot,'module_snapshot_hash':digest(snapshot),
            'local_module_hash':{'algorithm':'sha256-json-stringify','value':hashlib.sha256(meta['snapshot_json'].encode()).hexdigest()},
            'capabilities':{'protocol_version':2,'schema_version':2,'object_types':['ResearchRun','Note']},
            'principal':public_principal,'principal_map':[public_principal],
            'trust':{'membership_epoch':current['membership_epoch'],'key_epoch':current['key_epoch'],
                'manifest_head':digest(current),'owner_root':meta['owner_root'],'recovery_root':meta['recovery_root'],'manifest_chain':chain}}
    wrapper=signed_object('PcProjectBinding',{'version':1,'binding':binding},owner.signing_seed)
    return Node(binding,wrapper,TrustedContext(meta['principal']),owner,key,runtime)

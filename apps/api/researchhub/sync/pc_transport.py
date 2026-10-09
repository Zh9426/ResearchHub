"""Durable PC QA outbox bridge. Crypto runs after identity commit, before CAS."""
from uuid import uuid4
from dataclasses import replace
import time
from sqlalchemy import String, LargeBinary, Integer, BigInteger, select
from sqlalchemy.orm import Mapped,mapped_column,Session
from packages.secure_wire.canonical import canonical_bytes,digest,strict_loads
from packages.secure_wire.membership import member_of,verify_active_envelope
from .pc_records import PcBase,RecordCommand
from .models import Outbox,Inbox
from .secure.transport_pg import locked,SealedOutbox,guard
from .secure.nonce import NonceVault
from .secure.envelope import seal_transaction
from .protocol import transaction_digest

class PcWire(PcBase):
    __tablename__='qa_pc_wire'
    transaction_id:Mapped[str]=mapped_column(String(36),primary_key=True)
    project:Mapped[str]=mapped_column(String(36))
    message:Mapped[str]=mapped_column(String(36),unique=True)
    token:Mapped[str]=mapped_column(String(36))
    source:Mapped[bytes]=mapped_column(LargeBinary)
    manifest_digest:Mapped[str]=mapped_column(String(64))
    object_type:Mapped[str]=mapped_column(String(32))
    object_id:Mapped[str]=mapped_column(String(36))
    work_version:Mapped[int]=mapped_column(Integer)
    body:Mapped[bytes|None]=mapped_column(LargeBinary,nullable=True)

def view(row):
    return dict(transaction_id=row.transaction_id,message_id=row.message,body=row.body,
        work_version=row.work_version,object_id=row.object_id,object_type=row.object_type)

class ManualClaim(PcBase):
    __tablename__='qa_pc_manual_claim'
    project:Mapped[str]=mapped_column(String(36),primary_key=True)
    token:Mapped[str]=mapped_column(String(36))
    expires:Mapped[int]=mapped_column(BigInteger)

class PcTransportFact(PcBase):
    __tablename__='qa_pc_transport_facts'
    project:Mapped[str]=mapped_column(String(36),primary_key=True)
    message:Mapped[str]=mapped_column(String(36),primary_key=True)
    kind:Mapped[str]=mapped_column(String(64),primary_key=True)
    body:Mapped[bytes]=mapped_column(LargeBinary)

class PcTransport:
    def __init__(self,engine,node):
        guard(engine);self.engine=engine;self.node=node
        PcBase.metadata.create_all(engine)

    def snapshot(self,transaction_id):
        with Session(self.engine) as db:
            row=db.get(PcWire,transaction_id)
            return view(row) if row else None

    def prepare(self,transaction_id,*,barrier=None,claim_token=None):
        token=str(uuid4());project=self.node.binding['opaque_project_id']
        with Session(self.engine) as db,db.begin():
            _,history=locked(db,project);manifest=history[-1]
            if claim_token:self.check_in_session(db,claim_token)
            if manifest['key_epoch']!=self.node.binding['trust']['key_epoch']:raise ValueError('LOADED_KEY_EPOCH_BLOCKED')
            member=member_of(manifest,self.node.owner.device_id,roles=('owner','writer'))
            command=db.scalar(select(RecordCommand).where(RecordCommand.transaction_id==transaction_id))
            out=db.get(Outbox,transaction_id)
            if not command or not out or command.project_id!=self.node.binding['semantic_project_id']:
                raise ValueError('DURABLE_COMMAND_REQUIRED')
            tx=out.envelope['transaction'];source=canonical_bytes(tx)
            if tx['device_id']!=self.node.owner.device_id:raise ValueError('DEVICE_MISMATCH')
            row=db.get(PcWire,transaction_id)
            if row:
                if row.project!=project or row.source!=source or row.manifest_digest!=digest(manifest):raise ValueError('WIRE_IDENTITY_OR_EPOCH_CHANGED')
                if row.body:
                    cached_envelope=strict_loads(row.body)
                    verify_active_envelope(cached_envelope,manifest)
                    self.bind_envelope(cached_envelope,tx,row.message,manifest)
                    cached=db.get(SealedOutbox,(project,row.message))
                    if not cached or cached.body!=row.body:raise ValueError('SEALED_OUTBOX_MISMATCH')
                    return view(row)
                row.token=token
            else:
                change=tx['changes'][0]
                row=PcWire(transaction_id=transaction_id,project=project,message=str(uuid4()),token=token,
                    source=source,manifest_digest=digest(manifest),object_type=change['object_type'],
                    object_id=change['object_id'],work_version=command.result['work_version'])
                db.add(row)
            db.flush();message=row.message
        if barrier:barrier('after_prepare')
        envelope=seal_transaction(tx,self.node.project_key,self.node.owner.signing_seed,
            NonceVault(self.node.runtime/'nonce.sqlite'),member['nonce_prefix'],opaque_project_id=project,
            sender_device_id=self.node.owner.device_id,membership_epoch=manifest['membership_epoch'],
            key_epoch=manifest['key_epoch'],message_id=message)
        raw=canonical_bytes(envelope)
        if barrier:barrier('before_commit')
        with Session(self.engine) as db,db.begin():
            _,current=locked(db,project);row=db.get(PcWire,transaction_id)
            if claim_token:self.check_in_session(db,claim_token)
            if row.token!=token or row.body or row.source!=source or digest(current[-1])!=digest(manifest):raise ValueError('WIRE_PREPARE_CAS')
            verify_active_envelope(envelope,current[-1])
            self.bind_envelope(envelope,tx,row.message,current[-1])
            if db.get(SealedOutbox,(project,message)):raise ValueError('SEALED_IDENTITY_COLLISION')
            row.body=raw;db.add(SealedOutbox(project=project,message=message,body=raw));db.flush()
            result=view(row)
        if barrier:barrier('after_commit')
        return result


    def claim(self):
        token=str(uuid4());now=int(time.time())
        with Session(self.engine) as db,db.begin():
            project=self.node.binding['opaque_project_id'];locked(db,project)
            row=db.get(ManualClaim,project)
            if row and row.expires>now:raise ValueError('MANUAL_SYNC_BUSY')
            if row:row.token=token;row.expires=now+120
            else:db.add(ManualClaim(project=project,token=token,expires=now+120))
        return token

    def check_in_session(self,db,token):
        row=db.scalar(select(ManualClaim).where(ManualClaim.project==self.node.binding['opaque_project_id']).with_for_update())
        if not row or row.token!=token or row.expires<=int(time.time()):raise ValueError('MANUAL_CLAIM_LOST')
        row.expires=int(time.time())+120

    def check(self,token):
        with Session(self.engine) as db,db.begin():
            locked(db,self.node.binding['opaque_project_id']);self.check_in_session(db,token)

    def release(self,token):
        with Session(self.engine) as db,db.begin():
            locked(db,self.node.binding['opaque_project_id']);row=db.get(ManualClaim,self.node.binding['opaque_project_id'])
            if row and row.token==token:row.expires=0

    def cycle(self,transport):
        """One explicit bounded cycle; no retries or background scheduling."""
        from .secure.receiver import receive
        from .secure.transport_pg import Trust,Received
        from .record_policy import apply_record_in_session
        from .pc_records import complete_handoff
        from .models import SyncTransaction
        from packages.secure_wire.peer_receipt import verify_peer_receipt
        from packages.secure_wire.membership import fields
        from packages.secure_wire.envelope import safe_int
        token=self.claim();project=self.node.binding['opaque_project_id'];semantic=self.node.binding['semantic_project_id']
        sent=received=confirmed=0
        unfinished=False;primary=None
        try:
            with Session(self.engine) as db,db.begin():
                _,history=locked(db,project);manifest=history[-1]
                peers=[m['device_id'] for m in manifest['members'] if m['status']=='ACTIVE' and m['device_id']!=self.node.owner.device_id]
                if len(peers)!=1:raise ValueError('EXACT_PEER_TARGET_REQUIRED')
                target=peers[0];epoch=manifest['key_epoch'];head=digest(manifest)
                if epoch!=self.node.binding['trust']['key_epoch']:raise ValueError('LOADED_KEY_EPOCH_BLOCKED')
            def check(db=None):
                if db is None:
                    with Session(self.engine) as own,own.begin():check(own)
                else:
                    _,now=locked(db,project)
                    if digest(now[-1])!=head:raise ValueError('AUTHORIZATION_CHANGED')
                    self.check_in_session(db,token)
            def request(method,path,body=None,query=None):
                check();result=transport.request(method,path,body,query);check();return result
            def pull():
                nonlocal received
                with Session(self.engine) as db:
                    cursor=db.get(Trust,project).cursor
                page=request('GET','/v1/messages',query={'cursor':cursor,'limit':100})
                receive(self.engine,project,self.node.owner,{epoch:self.node.project_key},page,cursor,
                    apply_record=lambda db,tx,ctx:apply_record_in_session(db,tx,replace(ctx,mode='offline_proposal',grant_id=None) if all(c['operation']=='resolve' for c in tx['changes']) else ctx,self.node.binding['module_snapshot'],project_id=semantic),commit_guard=check)
                received+=len(page['rows'])
                return bool(page['has_more'])
            more=pull()
            if not more:
                with Session(self.engine) as db:
                    transactions=list(db.scalars(select(Outbox.transaction_id).join(Inbox,Inbox.transaction_id==Outbox.transaction_id).where(Outbox.project_id==semantic).order_by(Inbox.sequence)))
                    pending=[tid for tid in transactions if not (db.get(PcWire,tid) and db.get(PcTransportFact,(project,db.get(PcWire,tid).message,'relay')))]
                unfinished=len(pending)>16
                for tid in pending[:16]:
                    check();row=self.prepare(tid,claim_token=token);check();env=strict_loads(row['body'])
                    result=request('POST','/v1/messages',{'envelopes':[env]})
                    fields(result,frozenset(('receipts',)))
                    if len(result['receipts'])!=1:raise ValueError('RELAY_RECEIPT_MISMATCH')
                    ack=result['receipts'][0]
                    fields(ack,frozenset(('stage','message_id','sequence','envelope_digest','chain_digest')))
                    safe_int(ack['sequence'],1)
                    if ack['stage']!='RELAY_STORED' or ack['message_id']!=row['message_id'] or ack['envelope_digest']!=digest(env):raise ValueError('RELAY_RECEIPT_MISMATCH')
                    with Session(self.engine) as db,db.begin():
                        locked(db,project);check(db);key=(project,row['message_id'],'relay');saved=db.get(PcTransportFact,key);raw=canonical_bytes(ack)
                        if saved and saved.body!=raw:raise ValueError('RELAY_RECEIPT_CHANGED')
                        if not saved:db.add(PcTransportFact(project=project,message=row['message_id'],kind='relay',body=raw))
                    sent+=1
                more=pull()
            # Revisit durable pages after response loss; signing cache is immutable.
            with Session(self.engine) as db:
                items=list(db.scalars(select(Received).where(Received.project==project).order_by(Received.sequence)))
                sequences=[r.sequence for r in items if strict_loads(r.body)['sender_device_id']!=self.node.owner.device_id and strict_loads(r.body)['membership_epoch']==manifest['membership_epoch'] and not db.get(PcTransportFact,(project,strict_loads(r.body)['message_id'],'published'))]
            unfinished=unfinished or len(sequences)>100
            for sequence in sequences[:100]:
                check();raw=transport.prepare_peer_receipt(sequence,commit_guard=check);check()
                result=request('POST','/v1/peer-receipts',strict_loads(raw))
                if canonical_bytes(result)!=raw:raise ValueError('PEER_RECEIPT_RELAY_MISMATCH')
                with Session(self.engine) as db,db.begin():
                    locked(db,project);check(db);message=strict_loads(raw)['message_id'];old=db.get(PcTransportFact,(project,message,'published'))
                    if old and old.body!=raw:raise ValueError('PEER_RECEIPT_CHANGED')
                    if not old:db.add(PcTransportFact(project=project,message=message,kind='published',body=raw))
            with Session(self.engine) as db:
                rows=[view(r) for r in db.scalars(select(PcWire).where(PcWire.project==project)) if r.body and not db.get(PcTransportFact,(project,r.message,'peer:'+target))]
            unfinished=unfinished or len(rows)>100
            for row in rows[:100]:
                result=request('GET','/v1/peer-receipts',query={'message_id':row['message_id'],'target_device_id':target})
                fields(result,frozenset(('receipt',)))
                if result['receipt'] is None:
                    unfinished=True;continue
                with Session(self.engine) as db,db.begin():
                    _,current=locked(db,project);check(db)
                    if digest(current[-1])!=head:raise ValueError('AUTHORIZATION_CHANGED')
                    ack=db.get(PcTransportFact,(project,row['message_id'],'relay'))
                    if not ack:raise ValueError('RELAY_SEQUENCE_REQUIRED')
                    receipt=verify_peer_receipt(result['receipt'],current[-1],strict_loads(row['body']),strict_loads(ack.body)['sequence'],target)
                    # Require our complete verified echo too, before changing local work state.
                    durable=db.get(Received,(project,receipt['sequence']))
                    if not durable or durable.body!=row['body']:continue
                    kind='peer:'+target;raw=canonical_bytes(receipt);old=db.get(PcTransportFact,(project,row['message_id'],kind))
                    if old and old.body!=raw:raise ValueError('PEER_RECEIPT_CHANGED')
                    if not old:db.add(PcTransportFact(project=project,message=row['message_id'],kind=kind,body=raw))
                    complete_handoff(db,semantic,row['object_type'],row['object_id'],row['transaction_id'],row['work_version'])
                    confirmed+=1
            return {'sent':sent,'received':received,'confirmed':confirmed,'has_more':more or unfinished,'peer':'VERIFIED' if confirmed else 'UNCONFIRMED','review':'NOT_REQUESTED'}
        except Exception as exc:
            primary=exc;raise
        finally:
            try:self.release(token)
            except Exception as cleanup:
                if primary:raise ExceptionGroup('SYNC_AND_CLEANUP_FAILED',[primary,cleanup]) from None
                raise



    def bind_envelope(self,envelope,tx,message,manifest):
        expected={'message_id':message,'opaque_project_id':self.node.binding['opaque_project_id'],
            'sender_device_id':self.node.owner.device_id,'membership_epoch':manifest['membership_epoch'],
            'key_epoch':manifest['key_epoch'],'semantic_transaction_digest':transaction_digest(tx),
            'protocol_version':tx['protocol_version'],'schema_version':tx['schema_version'],'record_type':'transaction',
            'dependencies':tx['dependencies']}
        if any(envelope[k]!=v for k,v in expected.items()):raise ValueError('WIRE_ENVELOPE_BINDING_MISMATCH')


def record_status(db,node,kind,object_id,manifest):
    """Whitelist projection for the latest saved local command, never scientific approval."""
    from .pc_records import read_record
    from packages.secure_wire.peer_receipt import verify_peer_receipt
    from packages.secure_wire.envelope import safe_int
    view_=read_record(db,node.binding['semantic_project_id'],kind,object_id);work=view_['work']
    peers=[m['device_id'] for m in manifest['members'] if m['status']=='ACTIVE' and m['device_id']!=node.owner.device_id]
    target=peers[0] if len(peers)==1 else None
    value={'object_id':object_id,'operation_id':None,'transaction_id':work['last_local_tx'] if work else None,
        'local_version':work['version'] if work else None,'local':'SAVED' if work else 'REMOTE_ONLY',
        'conversion':'NOT_CONVERTED' if work else 'NOT_APPLICABLE','transport':'NOT_SENT' if work else 'NOT_APPLICABLE',
        'peer':'UNCONFIRMED','target_device_id':target,'review':'NOT_REQUESTED',
        'current_record':view_['trusted']['status'].upper(),'state_at_commit':None}
    if not work or not work['last_local_tx']:return value
    row=db.get(PcWire,work['last_local_tx'])
    if not row:return value
    if row.project!=node.binding['opaque_project_id'] or row.object_id!=object_id or row.object_type!=kind or row.work_version!=work['version']:
        raise ValueError('STATUS_IDENTITY_MISMATCH')
    value['operation_id']=row.transaction_id;value['conversion']='SEALED' if row.body else 'PREPARED'
    if row.manifest_digest!=digest(manifest):
        value.update(conversion='BLOCKED',transport='BLOCKED');return value
    if not row.body:return value
    env=strict_loads(row.body);verify_active_envelope(env,manifest)
    tx=strict_loads(row.source)
    if env['message_id']!=row.message or env['opaque_project_id']!=row.project or env['sender_device_id']!=node.owner.device_id or env['semantic_transaction_digest']!=transaction_digest(tx) or tx['transaction_id']!=row.transaction_id:
        raise ValueError('STATUS_ENVELOPE_MISMATCH')
    relay=db.get(PcTransportFact,(row.project,row.message,'relay'))
    if not relay:return value
    ack=strict_loads(relay.body);safe_int(ack['sequence'],1)
    if ack['stage']!='RELAY_STORED' or ack['message_id']!=row.message or ack['envelope_digest']!=digest(env):raise ValueError('STATUS_RELAY_MISMATCH')
    value['transport']='RELAY_STORED'
    peer=db.get(PcTransportFact,(row.project,row.message,'peer:'+target)) if target else None
    if peer:
        receipt=verify_peer_receipt(strict_loads(peer.body),manifest,env,ack['sequence'],target)
        value['peer']='VERIFIED';value['state_at_commit']=receipt['state_at_commit']
    return value

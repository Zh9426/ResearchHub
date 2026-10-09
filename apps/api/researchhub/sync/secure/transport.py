"""QA-only trusted transport. Fixed verified TLS loopback; no plaintext fallback."""

import hashlib
import ssl
import time
from uuid import uuid4

import httpx
from sqlalchemy.orm import Session

from packages.secure_wire.canonical import canonical_bytes, digest, strict_loads
from packages.secure_wire.envelope import b64encode, validate_envelope
from packages.secure_wire.membership import member_of, verify_active_envelope
from packages.secure_wire.request import AUDIENCE, POST_PATHS, validate_query

from .keys import signed_object
from .receiver import checked_anchor, receive
from .transport_bounds import bounded_canonical, read_response
from .transport_pg import Received, SealedOutbox, guard, locked


class SecureTransport:
    def __init__(self, engine, project, device, cafile, keyring):
        guard(engine)
        self.engine, self.project, self.device = engine, project, device
        self.keyring = dict(keyring)
        context = ssl.create_default_context(cafile=cafile)
        self.http = httpx.Client(
            base_url="https://127.0.0.1:38001",
            verify=context,
            trust_env=False,
            follow_redirects=False,
            timeout=15,
        )

    def close(self):
        self.http.close()

    def enqueue(self, raw):
        if type(raw) is not bytes:
            raise ValueError("CANONICAL_BYTES_REQUIRED")
        envelope = strict_loads(raw)
        validate_envelope(envelope)
        if canonical_bytes(envelope) != raw:
            raise ValueError("NONCANONICAL_ENVELOPE")
        with Session(self.engine) as db, db.begin():
            _, history = locked(db, self.project)
            verify_active_envelope(envelope, history[-1])
            if envelope["sender_device_id"] != self.device.device_id:
                raise ValueError("DEVICE_MISMATCH")
            key = (self.project, envelope["message_id"])
            old = db.get(SealedOutbox, key)
            if old and old.body != raw:
                raise ValueError("OUTBOX_IDENTITY_COLLISION")
            if not old:
                db.add(
                    SealedOutbox(
                        project=self.project, message=envelope["message_id"], body=raw
                    )
                )

    def request(self, method, path, body=None, query=None):
        with Session(self.engine) as db, db.begin():
            _, history = locked(db, self.project)
            manifest = history[-1]
        return self._request_manifest(manifest, method, path, body, query)

    def pairing_request(self, session_id, operation, *, db):
        """Only this registered, verified journal may authorize fixed membership paths.

        No public trust/manifest override exists. The caller holds the PG project
        lock; signing revalidates both stored heads and the exact grant scope.
        """
        from ..pc_pairing import PairingJournal, RelayOldHead
        from packages.secure_wire.membership import verify_transition, verify_grant, verify_challenge
        trust, history = locked(db, self.project)
        row = db.get(PairingJournal, session_id)
        if (row is None or row.project != self.project or row.active_project != self.project
                or row.stage not in ('CONSUMED','RELAY_UNKNOWN','RELAY_CONFIRMED') or not row.receipt):
            raise ValueError('PAIRING_JOURNAL_REQUIRED')
        old = row.reserved['old']; candidate = row.receipt['manifest']
        if digest(history[-1]) != digest(old):raise ValueError('PAIRING_JOURNAL_HEAD')
        verify_transition(old,candidate,trust.recovery)
        verify_grant(row.receipt['grant'],candidate)
        verify_challenge(row.challenge,old,row.reserved['issued_at'])
        context=row.receipt['grant']['context']
        if (candidate['members'] != [*old['members'],row.reserved['recipient']]
                or candidate['key_epoch'] != old['key_epoch']
                or context['session_id'] != session_id
                or context['recipient_device_id'] != row.reserved['recipient']['device_id']
                or row.receipt['challenge_digest'] != digest(row.challenge)):
            raise ValueError('PAIRING_JOURNAL_SCOPE')
        member_of(old,self.device.device_id,roles=('owner',))
        if operation == 'receipt':
            try:
                return self._request_manifest(candidate,'GET','/v1/membership/receipt',
                    query={'candidate_digest':digest(candidate)})
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 401 and exc.response.content == canonical_bytes({'ok':False,'code':'AUTH_REJECTED'}):
                    raise RelayOldHead() from None
                raise
        if operation == 'current':return self._request_manifest(old,'GET','/v1/membership')
        if operation == 'publish':return self._request_manifest(old,'POST','/v1/membership',{'manifest':candidate})
        raise ValueError('PAIRING_OPERATION_REQUIRED')

    def _request_manifest(self, manifest, method, path, body=None, query=None):
        query = query or {}
        suffix = "&".join(f"{k}={query[k]}" for k in sorted(query))
        if method == "GET":
            validate_query(path, suffix.encode("ascii"))
            raw = b""
        elif method == "POST" and path in POST_PATHS and not query:
            raw = bounded_canonical(body)
        else:
            raise ValueError("INVALID_REQUEST")
        member_of(manifest, self.device.device_id)
        proof = signed_object(
            "RelayRequest",
            {
                "version": 1,
                "audience": AUDIENCE,
                "method": method,
                "path": path,
                "query": query,
                "opaque_project_id": self.project,
                "device_id": self.device.device_id,
                "membership_epoch": manifest["membership_epoch"],
                "key_epoch": manifest["key_epoch"],
                "manifest_digest": digest(manifest),
                "body_digest": hashlib.sha256(raw).hexdigest(),
                "request_id": str(uuid4()),
                "issued_at": int(time.time()),
            },
            self.device.signing_seed,
        )
        with self.http.stream(
            method,
            path + ("?" + suffix if suffix else ""),
            content=raw,
            headers={
                "content-type": "application/json",
                "accept-encoding": "identity",
                "x-rh-proof": b64encode(canonical_bytes(proof)),
            },
        ) as response:
            response_body = read_response(response)
            # Preserve only the bounded response so journal auth rejection can
            # be distinguished from an uncertain network/server outcome.
            response._content = response_body
            response.raise_for_status()
        value = strict_loads(response_body)
        if canonical_bytes(value) != response_body:
            raise ValueError("NONCANONICAL_RELAY_RESPONSE")
        if set(value) != {"ok", "result"} or value["ok"] is not True:
            raise ValueError("INVALID_RELAY_RESPONSE")
        return value["result"]

    def push(self, message_id):
        with Session(self.engine) as db:
            row = db.get(SealedOutbox, (self.project, message_id))
            if row is None:
                raise ValueError("OUTBOX_REQUIRED")
            envelope = strict_loads(row.body)
        # Fresh request UUID/time/current authorization; sealed bytes are never regenerated.
        return self.request("POST", "/v1/messages", {"envelopes": [envelope]})

    def pull(self, cursor, limit=100):
        return self.request(
            "GET", "/v1/messages", query={"cursor": cursor, "limit": limit}
        )

    def receive(self, page, start, **kwargs):
        return receive(
            self.engine, self.project, self.device, self.keyring, page, start, **kwargs
        )

    def ack(self, sequence):
        """Only persisted transport receipt authorizes ACK; never scientific acceptance."""
        with Session(self.engine) as db, db.begin():
            trust, history = locked(db, self.project)
            checked_anchor(trust, history)
            row = db.get(Received, (self.project, sequence))
            if row is None or sequence > trust.cursor:
                raise ValueError("DURABLE_RECEIPT_REQUIRED")
            envelope = strict_loads(row.body)
            ack = signed_object(
                "RelayAck",
                {
                    "version": 1,
                    "opaque_project_id": self.project,
                    "device_id": self.device.device_id,
                    "message_id": envelope["message_id"],
                    "sequence": sequence,
                    "stage": "DEVICE_DECRYPTED",
                    "retain_until_ack": True,
                },
                self.device.signing_seed,
            )
        return self.request("POST", "/v1/ack", ack)

    def accept_checkpoint(self, checkpoint):
        """A remote checkpoint cannot bypass locally verified complete history."""
        from packages.secure_wire.checkpoint import verify_checkpoint

        with Session(self.engine) as db, db.begin():
            trust, history = locked(db, self.project)
            checked_anchor(trust, history)
            verify_checkpoint(checkpoint, history[-1])
            if (checkpoint["cursor"], checkpoint["chain_digest"]) != (
                trust.cursor,
                trust.chain,
            ):
                raise ValueError("ROLLBACK_OR_UNCONSUMED_CHECKPOINT")
            trust.checkpoint = canonical_bytes(checkpoint)
        return checkpoint


    def prepare_peer_receipt(self, sequence, *, commit_guard=None):
        """Sign only committed receiver state; cache exact bytes before any HTTP."""
        from .transport_pg import PeerReceiptOutbox
        from packages.secure_wire.peer_receipt import receipt_body, verify_peer_receipt
        with Session(self.engine) as db, db.begin():
            trust, history = locked(db, self.project)
            if commit_guard: commit_guard(db)
            checked_anchor(trust, history)
            row = db.get(Received, (self.project, sequence))
            if row is None or sequence > trust.cursor:
                raise ValueError('DURABLE_RECEIPT_REQUIRED')
            envelope = strict_loads(row.body)
            result = strict_loads(row.result)
            if result.get('state') not in ('ACCEPTED', 'CANDIDATE'):
                raise ValueError('KERNEL_APPLIED_REQUIRED')
            # An old epoch remains historical: never re-sign it under current authority.
            manifest = history[-1]
            key = (self.project, sequence, self.device.device_id)
            saved = db.get(PeerReceiptOutbox, key)
            if saved:
                verify_peer_receipt(strict_loads(saved.body), manifest, envelope, sequence, self.device.device_id)
                return saved.body
            receipt = signed_object('PeerApplyReceipt', receipt_body(manifest, envelope, sequence,
                self.device.device_id, result['state']), self.device.signing_seed)
            verify_peer_receipt(receipt, manifest, envelope, sequence, self.device.device_id)
            raw = canonical_bytes(receipt)
            db.add(PeerReceiptOutbox(project=self.project, sequence=sequence, target=self.device.device_id, body=raw))
        return raw

    def publish_peer_receipt(self, sequence):
        raw = self.prepare_peer_receipt(sequence)
        result = self.request('POST', '/v1/peer-receipts', strict_loads(raw))
        if canonical_bytes(result) != raw:
            raise ValueError('PEER_RECEIPT_RELAY_MISMATCH')
        return result

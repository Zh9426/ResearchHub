"""Atomic trusted receive: validate a complete page before any Kernel mutation."""

from sqlalchemy.orm import Session

from packages.secure_wire.canonical import canonical_bytes, digest, strict_loads
from packages.secure_wire.checkpoint import extend_chain, verify_checkpoint
from packages.secure_wire.envelope import safe_int
from packages.secure_wire.membership import fields, member_of, verify_active_envelope

from ..authority import TrustedContext, principal_for
from ..kernel import apply_in_session
from .checkpoint import sign_checkpoint
from .envelope import open_transaction
from .transport_bounds import bounded_canonical
from .transport_pg import Received, locked


def checked_anchor(row, history):
    if row.checkpoint is None:
        if row.cursor != 0 or row.chain != "0" * 64:
            raise ValueError("ANCHOR_REQUIRED")
        return
    checkpoint = strict_loads(row.checkpoint)
    manifest = next(
        (m for m in history if m["membership_epoch"] == checkpoint["membership_epoch"]),
        None,
    )
    if manifest is None:
        raise ValueError("UNPINNED_CHECKPOINT")
    verify_checkpoint(checkpoint, manifest)
    if (
        checkpoint["cursor"],
        checkpoint["chain_digest"],
        checkpoint["opaque_project_id"],
    ) != (row.cursor, row.chain, row.project):
        raise ValueError("CHECKPOINT_BINDING_MISMATCH")


def receive(
    engine, project, creator, keyring, page, start, *, grants=None, barrier=None
):
    # Snapshot untrusted inputs before validation or any database wait.
    page = strict_loads(bounded_canonical(page))
    fields(page, frozenset(("rows", "cursor", "chain_digest", "has_more")))
    safe_int(start)
    safe_int(page["cursor"])
    if (
        type(page["has_more"]) is not bool
        or type(page["rows"]) is not list
        or len(page["rows"]) > 100
    ):
        raise ValueError("INVALID_PAGE")
    if page["cursor"] != start + len(page["rows"]) or (
        not page["rows"] and page["has_more"]
    ):
        raise ValueError("CURSOR_GAP")
    grants = dict(grants or {})
    with Session(engine) as db, db.begin():
        trust, history = locked(db, project)
        checked_anchor(trust, history)
        current = history[-1]
        member_of(current, creator.device_id)
        if start > trust.cursor:
            raise ValueError("CURSOR_GAP")
        prior = db.get(Received, (project, start)) if start else None
        if start and prior is None:
            raise ValueError("CURSOR_GAP")
        chain = prior.chain if prior else "0" * 64
        prepared = []
        principals = strict_loads(trust.principals)
        for seq, item in enumerate(page["rows"], start + 1):
            fields(
                item,
                frozenset(("sequence", "envelope_digest", "chain_digest", "envelope")),
            )
            safe_int(item["sequence"], 1)
            if (
                item["sequence"] != seq
                or digest(item["envelope"]) != item["envelope_digest"]
            ):
                raise ValueError("PAGE_BINDING_MISMATCH")
            chain = extend_chain(
                chain,
                seq - 1,
                [{"sequence": seq, "envelope_digest": item["envelope_digest"]}],
            )
            if chain != item["chain_digest"]:
                raise ValueError("CHAIN_DIGEST_MISMATCH")
            raw = canonical_bytes(item["envelope"])
            old = db.get(Received, (project, seq))
            if seq <= trust.cursor:
                if old is None or (old.body, old.digest, old.chain) != (
                    raw,
                    item["envelope_digest"],
                    chain,
                ):
                    raise ValueError("CONSUMED_PAGE_REPLACED")
                prepared.append((item, old, None, None))
                continue
            envelope = item["envelope"]
            manifest = next(
                (
                    m
                    for m in history
                    if m["membership_epoch"] == envelope["membership_epoch"]
                ),
                None,
            )
            if manifest is None:
                raise ValueError("UNPINNED_MEMBERSHIP_HISTORY")
            verify_active_envelope(envelope, manifest)
            member = member_of(
                manifest, envelope["sender_device_id"], roles=("owner", "writer")
            )
            key = keyring.get(envelope["key_epoch"])
            if key is None:
                raise ValueError("UNKNOWN_KEY_EPOCH")
            tx = open_transaction(
                envelope,
                key,
                bytes.fromhex(member["signing_public_key"]),
                project_id=trust.semantic_project,
                opaque_project_id=project,
                sender_device_id=member["device_id"],
                membership_epoch=manifest["membership_epoch"],
                key_epoch=manifest["key_epoch"],
                nonce_prefix=member["nonce_prefix"],
            )
            context = None
            if manifest == current:
                principal = principals.get(member["device_id"])
                if principal is None:
                    raise ValueError("LOCAL_PRINCIPAL_REQUIRED")
                context = TrustedContext(
                    principal, grants.get(tx["transaction_id"]), relay_seq=None
                )
                principal_for(db, context, tx)
            prepared.append((item, None, tx, context))
        if chain != page["chain_digest"]:
            raise ValueError("CHAIN_DIGEST_MISMATCH")
        results = []
        for item, old, tx, context in prepared:
            if old is not None:
                results.append(strict_loads(old.result))
                continue
            result = (
                apply_in_session(db, tx, context)
                if context
                else {"state": "TRANSPORT_QUARANTINED", "reason": "HISTORICAL_EPOCH"}
            )
            db.add(
                Received(
                    project=project,
                    sequence=item["sequence"],
                    body=canonical_bytes(item["envelope"]),
                    digest=item["envelope_digest"],
                    chain=item["chain_digest"],
                    result=canonical_bytes(result),
                )
            )
            results.append(result)
        if page["cursor"] > trust.cursor:
            trust.cursor, trust.chain = page["cursor"], chain
            trust.checkpoint = canonical_bytes(
                sign_checkpoint(current, creator, trust.cursor, chain)
            )
        db.flush()
        if barrier:
            barrier("before_commit")
    if barrier:
        barrier("after_commit")
    return results

"""Public PeerApplyReceipt v1 verification. A receipt records historical application only.

The caller supplies an already pinned manifest and its expected concrete peer. This
module never promotes an old epoch receipt into current authorization or DAG state.
"""
from .canonical import digest
from .envelope import safe_int, uuid, hex_bytes, b64decode
from .membership import fields, member_of, verify_signed, verify_active_envelope

RECEIPT_FIELDS = frozenset('version opaque_project_id sender_device_id target_device_id message_id sequence envelope_digest semantic_transaction_digest membership_epoch key_epoch manifest_digest stage state_at_commit signature'.split())


def validate_peer_receipt(value):
    fields(value, RECEIPT_FIELDS)
    safe_int(value['version'], 1, 1)
    for key in ('opaque_project_id', 'sender_device_id', 'target_device_id', 'message_id'):
        uuid(value[key])
    for key in ('sequence', 'membership_epoch', 'key_epoch'):
        safe_int(value[key], 1)
    for key in ('envelope_digest', 'semantic_transaction_digest', 'manifest_digest'):
        hex_bytes(value[key], 32)
    b64decode(value['signature'], 64)
    if value['stage'] != 'KERNEL_APPLIED' or value['state_at_commit'] not in ('ACCEPTED', 'CANDIDATE'):
        raise ValueError('INVALID_PEER_RECEIPT')
    return value


def receipt_body(manifest, envelope, sequence, target, state):
    safe_int(sequence, 1)
    uuid(target)
    return dict(version=1, opaque_project_id=envelope['opaque_project_id'],
        sender_device_id=envelope['sender_device_id'], target_device_id=target,
        message_id=envelope['message_id'], sequence=sequence, envelope_digest=digest(envelope),
        semantic_transaction_digest=envelope['semantic_transaction_digest'],
        membership_epoch=envelope['membership_epoch'], key_epoch=envelope['key_epoch'],
        manifest_digest=digest(manifest), stage='KERNEL_APPLIED', state_at_commit=state)


def verify_peer_receipt(value, manifest, envelope, sequence, target):
    validate_peer_receipt(value)
    verify_active_envelope(envelope, manifest)
    expected = receipt_body(manifest, envelope, sequence, target, value['state_at_commit'])
    if any(value[key] != item for key, item in expected.items()):
        raise ValueError('PEER_RECEIPT_BINDING_MISMATCH')
    member = member_of(manifest, target)
    verify_signed('PeerApplyReceipt', value, member['signing_public_key'])
    return value

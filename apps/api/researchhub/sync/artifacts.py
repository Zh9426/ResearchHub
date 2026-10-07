"""Synthetic QA verification registry; bytes never enter kernel rows or cloud."""

from hashlib import sha256

from .models import VerifiedArtifact
from .protocol import ProtocolError


def register_verified_reference(db, project_id, key_epoch, data, *, checksum=None, size=None):
    if type(data) is not bytes or type(key_epoch) is not int or key_epoch < 0:
        raise ProtocolError('ARTIFACT_INVALID', 'synthetic bytes and epoch required')
    actual, length = sha256(data).hexdigest(), len(data)
    if (checksum is not None and checksum != actual) or (size is not None and size != length):
        raise ProtocolError('CHECKSUM_MISMATCH', 'QA byte verification failed')
    key = (project_id, key_epoch, actual, length)
    row = db.get(VerifiedArtifact, key)
    if row is None:
        row = VerifiedArtifact(project_id=project_id, key_epoch=key_epoch, checksum=actual, size=length)
        db.add(row)
        db.flush()
    return {'checksum': actual, 'size': length, 'key_epoch': key_epoch}


def validate_artifact(db, project_id, document):
    if document.get('availability') != 'verified_reference':
        return
    checksum = document.get('checksum', document.get('sha256'))
    epoch, size = document.get('key_epoch'), document.get('size')
    if (document.get('checksum') and document.get('sha256')
            and document['checksum'] != document['sha256']):
        raise ProtocolError('CHECKSUM_MISMATCH', 'conflicting artifact hashes')
    if checksum is None or epoch is None or size is None or db.get(
            VerifiedArtifact, (project_id, epoch, checksum, size)) is None:
        raise ProtocolError('ARTIFACT_UNVERIFIED', 'reference has no project/epoch verified QA receipt')

"""Backup format behavior; full PostgreSQL/MinIO drill is a separate runtime check."""
import hashlib
import json
import zipfile

import pytest
from botocore.exceptions import ClientError

from scripts import backup_data


def test_backup_before_any_artifact_creates_empty_export(tmp_path, monkeypatch):
    class S3:
        def head_bucket(self, **kw):
            raise ClientError({'Error': {'Code': '404'}}, 'HeadBucket')
        def get_paginator(self, operation): return self
        def paginate(self, **kw):
            raise ClientError({'Error': {'Code': 'NoSuchBucket'}}, 'ListObjectsV2')
    monkeypatch.setenv('S3_BUCKET', 'researchhub')
    monkeypatch.setattr(backup_data, 'client', lambda: S3())
    target = tmp_path / 'objects.zip'
    backup_data.export_objects(target)
    with zipfile.ZipFile(target) as archive:
        assert json.loads(archive.read('objects.json'))['objects'] == []


def test_corrupt_object_archive_rejected_before_any_upload(tmp_path, monkeypatch):
    uploads = []
    class S3:
        def upload_fileobj(self, *args, **kw): uploads.append(args)
    monkeypatch.setenv('S3_BUCKET', 'researchhub')
    monkeypatch.setattr(backup_data, 'client', lambda: S3())
    target = tmp_path / 'objects.zip'
    with zipfile.ZipFile(target, 'w') as archive:
        archive.writestr('objects/0.bin', b'changed')
        archive.writestr('objects.json', json.dumps({'format_version': 1, 'objects': [{'key': '../data', 'entry': 'objects/0.bin', 'size': 7, 'sha256': hashlib.sha256(b'original').hexdigest()}]}))
    with pytest.raises(ValueError, match='checksum'):
        backup_data.restore_objects(target)
    assert uploads == []


def test_restore_refuses_nonempty_bucket(tmp_path, monkeypatch):
    class S3:
        def head_bucket(self, **kw): pass
        def list_objects_v2(self, **kw): return {'KeyCount': 1}
    monkeypatch.setenv('S3_BUCKET', 'researchhub')
    monkeypatch.setattr(backup_data, 'client', lambda: S3())
    target = tmp_path / 'objects.zip'
    with zipfile.ZipFile(target, 'w') as archive:
        archive.writestr('objects.json', json.dumps({'format_version': 1, 'objects': []}))
    with pytest.raises(ValueError, match='empty'):
        backup_data.restore_objects(target)

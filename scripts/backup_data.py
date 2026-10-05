"""Logical S3 export/import, used inside the API image by explicit backup commands."""
import argparse
import hashlib
import json
import os
import tempfile
import zipfile
from pathlib import Path

import boto3
from botocore.exceptions import ClientError


def client():
    return boto3.client('s3', endpoint_url=os.environ['S3_ENDPOINT_URL'],
                        aws_access_key_id=os.environ['S3_ACCESS_KEY'],
                        aws_secret_access_key=os.environ['S3_SECRET_KEY'])


def export_objects(path: Path):
    s3 = client()
    bucket = os.environ['S3_BUCKET']
    records = []
    try:
        s3.head_bucket(Bucket=bucket)
        pages = s3.get_paginator('list_objects_v2').paginate(Bucket=bucket)
    except ClientError as error:
        if str(error.response['Error']['Code']) not in ('404', 'NoSuchBucket'):
            raise
        pages = []
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_STORED, allowZip64=True) as archive:
        for page in pages:
            for obj in page.get('Contents', []):
                response = s3.get_object(Bucket=bucket, Key=obj['Key'])
                digest = hashlib.sha256()
                entry = f'objects/{len(records)}.bin'
                size = 0
                try:
                    with archive.open(entry, 'w', force_zip64=True) as target:
                        for chunk in response['Body'].iter_chunks(1024 * 1024):
                            digest.update(chunk)
                            size += len(chunk)
                            target.write(chunk)
                finally:
                    response['Body'].close()
                records.append({'key': obj['Key'], 'entry': entry, 'size': size,
                                'sha256': digest.hexdigest(), 'content_type': response.get('ContentType'),
                                'metadata': response.get('Metadata', {})})
        archive.writestr('objects.json', json.dumps({'format_version': 1, 'bucket': bucket, 'objects': records}))
    print(f'Exported {len(records)} objects')


def restore_objects(path: Path):
    s3 = client()
    bucket = os.environ['S3_BUCKET']
    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read('objects.json'))
        if manifest.get('format_version') != 1:
            raise ValueError('Unsupported object backup format')
        # Verify ALL bytes before writing any object; never extract archive paths.
        for obj in manifest['objects']:
            digest = hashlib.sha256()
            size = 0
            with archive.open(obj['entry']) as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b''):
                    digest.update(chunk)
                    size += len(chunk)
            if digest.hexdigest() != obj['sha256'] or size != obj['size']:
                raise ValueError('Object backup checksum mismatch')
        try:
            s3.head_bucket(Bucket=bucket)
        except s3.exceptions.ClientError as error:
            if str(error.response['Error']['Code']) not in ('404', 'NoSuchBucket'):
                raise
            s3.create_bucket(Bucket=bucket)
        if s3.list_objects_v2(Bucket=bucket, MaxKeys=1).get('KeyCount', 0):
            raise ValueError('Restore destination bucket must be empty; existing objects will not be overwritten')
        for obj in manifest['objects']:
            with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) as source:
                with archive.open(obj['entry']) as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                        source.write(chunk)
                source.seek(0)
                kwargs = {'Metadata': obj.get('metadata', {})}
                if obj.get('content_type'):
                    kwargs['ContentType'] = obj['content_type']
                s3.upload_fileobj(source, bucket, obj['key'], ExtraArgs=kwargs)
    print(f'Restored {len(manifest["objects"])} objects')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['export', 'restore'])
    parser.add_argument('path', type=Path)
    args = parser.parse_args()
    (export_objects if args.action == 'export' else restore_objects)(args.path)

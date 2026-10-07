"""S3-compatible storage: objects are private; downloads pass authorization."""

import os

import boto3
from botocore.exceptions import ClientError

ALLOWED_ARTIFACT_TYPES = {
    "png": {"image/png"},
    "jpg": {"image/jpeg"},
    "jpeg": {"image/jpeg"},
    "pdf": {"application/pdf"},
    "csv": {"text/csv", "application/csv", "text/plain"},
    "json": {"application/json", "text/plain"},
    "mat": {"application/octet-stream", "application/x-matlab-data"},
    "npy": {"application/octet-stream"},
    "npz": {"application/octet-stream", "application/zip"},
    "zip": {"application/zip", "application/x-zip-compressed"},
    "txt": {"text/plain"},
    "log": {"text/plain"},
    "mp4": {"video/mp4"},
    "webm": {"video/webm"},
}
ARTIFACT_SIGNATURES = {
    "png": b"\x89PNG\r\n\x1a\n",
    "jpg": b"\xff\xd8\xff",
    "jpeg": b"\xff\xd8\xff",
    "pdf": b"%PDF-",
}


def artifact_signature_valid(ext, prefix):
    if ext in ARTIFACT_SIGNATURES:
        return prefix.startswith(ARTIFACT_SIGNATURES[ext])
    if ext == "mp4":
        return (
            len(prefix) >= 16
            and prefix[4:8] == b"ftyp"
            and int.from_bytes(prefix[:4], "big") >= 16
            and prefix[8:12]
            in {
                b"isom",
                b"iso2",
                b"mp41",
                b"mp42",
                b"avc1",
                b"M4V ",
                b"dash",
                b"iso5",
                b"iso6",
            }
        )
    if ext == "webm":
        return prefix.startswith(b"\x1a\x45\xdf\xa3") and b"webm" in prefix
    return True


class S3Objects:
    def __init__(self):
        self.bucket = os.getenv("S3_BUCKET", "researchhub")
        if not os.getenv("S3_ACCESS_KEY") or not os.getenv("S3_SECRET_KEY"):
            raise ValueError("S3 credentials must be configured through environment")
        self.client = boto3.client(
            "s3",
            endpoint_url=os.getenv("S3_ENDPOINT_URL", "http://localhost:9000"),
            aws_access_key_id=os.getenv("S3_ACCESS_KEY"),
            aws_secret_access_key=os.getenv("S3_SECRET_KEY"),
            region_name=os.getenv("S3_REGION", "us-east-1"),
        )

    def ensure_bucket(self):
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError as e:
            if e.response["Error"]["Code"] in ("404", "NoSuchBucket"):
                self.client.create_bucket(Bucket=self.bucket)
            else:
                raise

    def put(self, key, stream, size, mime):
        self.ensure_bucket()
        self.client.upload_fileobj(
            stream, self.bucket, key, ExtraArgs={"ContentType": mime}
        )

    def get(self, key):
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"]

    def delete(self, key):
        self.client.delete_object(Bucket=self.bucket, Key=key)

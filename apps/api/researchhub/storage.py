"""S3-compatible storage: objects are private; downloads pass authorization."""

import os

import boto3
from botocore.exceptions import ClientError


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

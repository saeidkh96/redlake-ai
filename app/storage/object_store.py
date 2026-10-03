from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.core.config import Settings


@dataclass(frozen=True)
class StoredObject:
    key: str
    uri: str


class ObjectStore(Protocol):
    def ensure_ready(self) -> None: ...

    def put_bytes(self, key: str, body: bytes, content_type: str) -> StoredObject: ...


class FileSystemObjectStore:
    """A safe local object store for development and deterministic tests."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def ensure_ready(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def put_bytes(self, key: str, body: bytes, content_type: str) -> StoredObject:
        del content_type  # The filesystem preserves bytes; metadata lives in the catalog.
        self.ensure_ready()
        destination = (self.root / key).resolve()
        if self.root not in destination.parents:
            raise ValueError("Object key escapes the configured storage root")

        destination.parent.mkdir(parents=True, exist_ok=True)
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=".upload-", dir=destination.parent
        )
        try:
            with os.fdopen(file_descriptor, "wb") as temporary_file:
                temporary_file.write(body)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_name, destination)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)

        return StoredObject(key=key, uri=destination.as_uri())


class S3ObjectStore:
    """S3-compatible object store used by MinIO locally and cloud S3 in a deployment."""

    def __init__(self, settings: Settings) -> None:
        import boto3

        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
        )

    def ensure_ready(self) -> None:
        from botocore.exceptions import ClientError

        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError as error:
            error_code = error.response.get("Error", {}).get("Code")
            if error_code not in {"404", "NoSuchBucket", "NotFound"}:
                raise
            self.client.create_bucket(Bucket=self.bucket)

    def put_bytes(self, key: str, body: bytes, content_type: str) -> StoredObject:
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
        )
        return StoredObject(key=key, uri=f"s3://{self.bucket}/{key}")


def build_object_store(settings: Settings) -> ObjectStore:
    if settings.storage_backend == "filesystem":
        return FileSystemObjectStore(settings.storage_root)
    return S3ObjectStore(settings)

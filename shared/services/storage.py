"""
Cloud storage abstraction for generated/downloaded files.

Strategy pattern — three backends:

  none   → NoopStorage  — no server-side storage; caller streams directly to browser
  s3     → S3Storage    — upload to AWS S3, return presigned URL
  azure  → AzureStorage — upload to Azure Blob, return SAS URL  (TODO: implement)
  gcs    → GCSStorage   — upload to Google Cloud Storage        (TODO: implement)

Usage:
    backend = get_storage_backend()
    result = await backend.store(content, filename, retention_days)
    if result is None:
        # Use StreamingResponse
    else:
        url, expires_at = result
        # Return download_url + expires_at to the client
"""
from __future__ import annotations

import io
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Optional

from shared.compat import STANDALONE

if STANDALONE:
    from standalone.config import get_settings


class StorageBackend(ABC):
    @abstractmethod
    async def store(
        self, content: bytes, filename: str, retention_days: int
    ) -> Optional[tuple[str, datetime]]:
        """
        Upload content and return (presigned_url, expires_at), or None for direct streaming.
        """


class NoopStorage(StorageBackend):
    """No cloud storage — caller should stream content directly to the browser."""

    async def store(self, content: bytes, filename: str, retention_days: int) -> None:
        return None


class S3Storage(StorageBackend):
    """Upload to AWS S3 and return a presigned download URL."""

    def __init__(self, bucket: str, access_key: str, secret_key: str, region: str):
        self.bucket = bucket
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region

    async def store(
        self, content: bytes, filename: str, retention_days: int
    ) -> tuple[str, datetime]:
        try:
            import boto3  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError(
                "boto3 is required for S3 storage. Run: pip install boto3"
            ) from exc

        key = f"statement-tools/{uuid.uuid4().hex}/{filename}"
        expiry = timedelta(days=retention_days)
        expires_at = datetime.now(timezone.utc) + expiry

        s3 = boto3.client(
            "s3",
            region_name=self.region,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
        )

        s3.upload_fileobj(
            io.BytesIO(content),
            self.bucket,
            key,
            ExtraArgs={"ContentDisposition": f'attachment; filename="{filename}"'},
        )

        url: str = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=int(expiry.total_seconds()),
        )
        return url, expires_at


class AzureStorage(StorageBackend):
    """TODO: Azure Blob Storage implementation."""

    async def store(self, content: bytes, filename: str, retention_days: int):
        raise NotImplementedError("Azure storage support coming soon.")


class GCSStorage(StorageBackend):
    """TODO: Google Cloud Storage implementation."""

    async def store(self, content: bytes, filename: str, retention_days: int):
        raise NotImplementedError("GCS storage support coming soon.")


def get_storage_backend() -> StorageBackend:
    """Return the configured storage backend (reads from settings in standalone mode)."""
    if not STANDALONE:
        # In plugin mode default to noop — use the host app's cloud storage instead if needed
        return NoopStorage()

    settings = get_settings()
    backend = settings.storage_backend

    if backend == "s3":
        return S3Storage(
            bucket=settings.aws_s3_bucket,
            access_key=settings.aws_s3_access_key_id,
            secret_key=settings.aws_s3_secret_access_key,
            region=settings.aws_s3_region,
        )
    if backend == "azure":
        return AzureStorage()
    if backend == "gcs":
        return GCSStorage()

    return NoopStorage()

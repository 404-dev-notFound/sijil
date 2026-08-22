import uuid
from typing import Any

import boto3
from botocore.client import Config

from app.config.settings import get_settings


class ObjectStorageClient:
    """Thin wrapper around an S3-compatible client — real AWS S3 in production, MinIO
    (docker-compose) for local dev. Concrete, not abstracted behind a Protocol: unlike
    LLMClient (architecture doc Section 8), there's no near-term reason to swap
    providers beyond the S3 API itself.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._bucket = settings.object_storage_bucket

        client_kwargs: dict[str, Any] = {
            "aws_access_key_id": settings.object_storage_access_key,
            "aws_secret_access_key": settings.object_storage_secret_key,
            "region_name": settings.object_storage_region,
        }
        if settings.object_storage_endpoint:
            client_kwargs["endpoint_url"] = settings.object_storage_endpoint
            # MinIO needs path-style addressing; real S3 tolerates it too.
            client_kwargs["config"] = Config(s3={"addressing_style": "path"})

        self._client = boto3.client("s3", **client_kwargs)

    def ensure_bucket(self) -> None:
        """Idempotent — safe to call on every startup. Real deployments provision the
        bucket out-of-band instead; this exists for local dev/test convenience."""
        existing = {b["Name"] for b in self._client.list_buckets().get("Buckets", [])}
        if self._bucket not in existing:
            self._client.create_bucket(Bucket=self._bucket)

    def upload(self, *, key: str, body: bytes, content_type: str) -> None:
        self._client.put_object(
            Bucket=self._bucket, Key=key, Body=body, ContentType=content_type
        )

    def download(self, key: str) -> bytes:
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        body: bytes = response["Body"].read()
        return body

    def generate_presigned_url(self, key: str, *, expires_in_seconds: int) -> str:
        """A short-lived signed download URL, regenerated on each request rather than
        permanently public (API SPEC Section 12) — this is how a generated report ever
        leaves the bucket at all, since it's never served directly from a public one."""
        url: str = self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires_in_seconds,
        )
        return url

    @staticmethod
    def build_document_key(
        *,
        company_id: uuid.UUID,
        shipment_id: uuid.UUID,
        document_id: uuid.UUID,
        filename: str,
    ) -> str:
        # Non-guessable, tenant-prefixed key. Files are never served directly from a
        # public bucket (architecture doc Section 15) — downloads go through a
        # short-lived signed URL instead (generate_presigned_url above).
        return f"{company_id}/{shipment_id}/{document_id}/{filename}"

    @staticmethod
    def build_report_key(
        *, company_id: uuid.UUID, shipment_id: uuid.UUID, report_id: uuid.UUID
    ) -> str:
        return f"{company_id}/{shipment_id}/reports/{report_id}.pdf"

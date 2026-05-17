"""S3 audit sink with Object Lock (spec §5.1, §12).

Writes the redacted payload to S3 under `<tenant>/<kind>/<hash>` with
COMPLIANCE-mode retention. Boto3 is imported lazily so the rest of the
package can be used without the optional dependency.

Hash uniqueness already lives in `Auditor`; this sink trusts the key it gets.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from avengers.core.audit import AuditSink
from avengers.schemas.audit import AuditEvent

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    pass


class S3AuditSink(AuditSink):
    def __init__(
        self,
        *,
        bucket: str,
        prefix: str = "",
        retention_years: int = 7,
        kms_key_arn: str | None = None,
        client: object | None = None,
    ) -> None:
        self._bucket = bucket
        self._prefix = prefix.rstrip("/") + "/" if prefix else ""
        self._retention_years = retention_years
        self._kms_key_arn = kms_key_arn
        self._client = client  # injectable for tests

    def _ensure_client(self):  # type: ignore[no-untyped-def]
        if self._client is not None:
            return self._client
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError("boto3 not installed; install avengers[bedrock]") from exc
        self._client = boto3.client("s3")
        return self._client

    async def write(self, event: AuditEvent, redacted_payload: str) -> None:
        client = self._ensure_client()
        key = f"{self._prefix}{event.payload_ref}"
        kwargs = {
            "Bucket": self._bucket,
            "Key": key,
            "Body": redacted_payload.encode("utf-8"),
            "ContentType": "application/json",
            "ObjectLockMode": "COMPLIANCE",
            "ObjectLockRetainUntilDate": datetime.now(UTC)
            + timedelta(days=365 * self._retention_years),
            "Metadata": {
                "tenant-id": event.tenant_id,
                "kind": event.kind,
                "severity": event.severity,
                "actor": event.actor,
            },
        }
        if self._kms_key_arn:
            kwargs["ServerSideEncryption"] = "aws:kms"
            kwargs["SSEKMSKeyId"] = self._kms_key_arn
        # boto3 is sync — run in default executor.
        import asyncio

        await asyncio.get_running_loop().run_in_executor(
            None, lambda: client.put_object(**kwargs)
        )
        logger.debug("audit_written bucket=%s key=%s", self._bucket, key)

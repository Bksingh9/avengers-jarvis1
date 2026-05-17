"""S3 audit sink — verify the Object Lock + KMS args without a real S3."""

from __future__ import annotations

from datetime import UTC, datetime

from avengers.core.audit_s3 import S3AuditSink
from avengers.schemas.audit import AuditEvent


class _FakeS3:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def put_object(self, **kwargs):
        self.calls.append(kwargs)
        return {"ETag": "x"}


async def test_writes_with_object_lock_and_kms():
    fake = _FakeS3()
    sink = S3AuditSink(
        bucket="audit",
        prefix="acme",
        retention_years=7,
        kms_key_arn="arn:aws:kms:x",
        client=fake,
    )
    event = AuditEvent(
        ts=datetime.now(UTC),
        tenant_id="acme",
        actor="agent:research",
        kind="tool.invoke",
        target="exa_search.search",
        payload_hash="deadbeef",
        payload_ref="acme/tool.invoke/deadbeef",
        severity="info",
    )
    await sink.write(event, '{"q":"x"}')
    assert len(fake.calls) == 1
    args = fake.calls[0]
    assert args["Bucket"] == "audit"
    assert args["Key"] == "acme/acme/tool.invoke/deadbeef"
    assert args["ObjectLockMode"] == "COMPLIANCE"
    assert args["ServerSideEncryption"] == "aws:kms"
    assert args["SSEKMSKeyId"] == "arn:aws:kms:x"
    assert args["Metadata"]["tenant-id"] == "acme"


async def test_no_kms_when_unset():
    fake = _FakeS3()
    sink = S3AuditSink(bucket="b", client=fake, retention_years=1)
    event = AuditEvent(
        ts=datetime.now(UTC),
        tenant_id="t",
        actor="x",
        kind="k",
        target="t",
        payload_hash="h",
        payload_ref="t/k/h",
    )
    await sink.write(event, "{}")
    args = fake.calls[0]
    assert "ServerSideEncryption" not in args
    assert args["Key"] == "t/k/h"

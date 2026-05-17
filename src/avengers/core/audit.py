"""Audit emitter (spec §5.1 / §12).

Writes append-only `AuditEvent`s. Production binds the S3-with-Object-Lock
sink; tests bind `InMemoryAuditSink`. Payloads are redacted before hashing so
the hash matches what's archived.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

from avengers.core.redact import redact
from avengers.schemas.audit import AuditEvent, AuditSeverity

logger = logging.getLogger(__name__)


class AuditSink(Protocol):
    async def write(self, event: AuditEvent, redacted_payload: str) -> None: ...


class InMemoryAuditSink(AuditSink):
    """Buffer for tests."""

    def __init__(self) -> None:
        self.events: list[tuple[AuditEvent, str]] = []

    async def write(self, event: AuditEvent, redacted_payload: str) -> None:
        self.events.append((event, redacted_payload))


class Auditor:
    """Convenience wrapper that builds and ships events."""

    def __init__(self, sink: AuditSink, *, redact_payloads: bool = True) -> None:
        self._sink = sink
        self._redact = redact_payloads

    async def emit(
        self,
        *,
        tenant_id: str,
        actor: str,
        kind: str,
        target: str,
        payload: Any,
        severity: AuditSeverity = "info",
        correlation_id: str | None = None,
    ) -> AuditEvent:
        raw = json.dumps(payload, default=str, sort_keys=True)
        red = redact(raw).text if self._redact else raw
        payload_hash = hashlib.sha256(red.encode("utf-8")).hexdigest()
        event = AuditEvent(
            id=uuid4(),
            ts=datetime.now(UTC),
            tenant_id=tenant_id,
            actor=actor,
            kind=kind,
            target=target,
            payload_hash=payload_hash,
            payload_ref=f"{tenant_id}/{kind}/{payload_hash}",
            severity=severity,
            correlation_id=correlation_id,
        )
        await self._sink.write(event, red)
        logger.info(
            "audit kind=%s actor=%s tenant=%s target=%s severity=%s",
            kind,
            actor,
            tenant_id,
            target,
            severity,
        )
        return event

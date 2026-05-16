"""Approval / audit schemas (spec §8.3)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

ApprovalStatus = Literal["pending", "approved", "denied", "expired"]
AuditSeverity = Literal["info", "warn", "high", "critical"]


class ApprovalRequest(BaseModel):
    """A pending human-in-the-loop approval (spec §11.3)."""

    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    tenant_id: str
    requested_by_agent: str
    requested_for_user: str
    action: str
    payload: dict
    status: ApprovalStatus = "pending"
    created_at: datetime
    decided_at: datetime | None = None
    decided_by: str | None = None
    reason: str | None = None


class AuditEvent(BaseModel):
    """An append-only audit record. Payload itself lives in S3; we keep a hash."""

    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    ts: datetime
    tenant_id: str
    actor: str  # user id or "agent:<name>"
    kind: str  # e.g. "tool.invoke", "model.call", "policy.deny"
    target: str  # e.g. "snowflake.snowflake_query"
    payload_hash: str
    payload_ref: str  # S3 key
    severity: AuditSeverity = "info"
    correlation_id: str | None = None

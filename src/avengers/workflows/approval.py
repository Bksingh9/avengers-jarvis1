"""Human-in-the-loop approval workflow (spec §11.3).

Single in-process queue for v1 — production should plug in a durable backing
store (Postgres + Temporal signals). The `await_decision()` coroutine resolves
when a human approves/denies via `decide()`, or expires after `timeout_s`.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from avengers.schemas.audit import ApprovalRequest


class ApprovalTimeoutError(TimeoutError):
    pass


@dataclass(slots=True)
class _Pending:
    request: ApprovalRequest
    future: asyncio.Future[ApprovalRequest] = field(default_factory=lambda: asyncio.get_event_loop().create_future())


class ApprovalQueue:
    def __init__(self) -> None:
        self._by_id: dict[UUID, _Pending] = {}
        self._lock = asyncio.Lock()

    async def enqueue(self, request: ApprovalRequest) -> ApprovalRequest:
        async with self._lock:
            self._by_id[request.id] = _Pending(request=request)
            return request

    async def list_pending(self, tenant_id: str | None = None) -> list[ApprovalRequest]:
        async with self._lock:
            return [
                p.request
                for p in self._by_id.values()
                if p.request.status == "pending"
                and (tenant_id is None or p.request.tenant_id == tenant_id)
            ]

    async def decide(
        self,
        request_id: UUID,
        *,
        decided_by: str,
        decision: Literal["approved", "denied"],
        reason: str | None = None,
    ) -> ApprovalRequest:
        async with self._lock:
            pending = self._by_id.get(request_id)
            if pending is None:
                raise KeyError(f"no such approval: {request_id}")
            if pending.request.status != "pending":
                return pending.request
            updated = pending.request.model_copy(
                update={
                    "status": decision,
                    "decided_by": decided_by,
                    "decided_at": datetime.now(UTC),
                    "reason": reason,
                }
            )
            pending.request = updated
            if not pending.future.done():
                pending.future.set_result(updated)
            return updated

    async def await_decision(
        self,
        request_id: UUID,
        *,
        timeout_s: float = 600.0,
    ) -> ApprovalRequest:
        async with self._lock:
            pending = self._by_id.get(request_id)
            if pending is None:
                raise KeyError(f"no such approval: {request_id}")
            if pending.request.status != "pending":
                return pending.request
            fut = pending.future
        try:
            return await asyncio.wait_for(fut, timeout=timeout_s)
        except asyncio.TimeoutError as exc:
            async with self._lock:
                cur = self._by_id[request_id]
                if cur.request.status == "pending":
                    self._by_id[request_id].request = cur.request.model_copy(
                        update={"status": "expired", "decided_at": datetime.now(UTC)}
                    )
            raise ApprovalTimeoutError(f"approval {request_id} expired") from exc


async def request_approval(
    queue: ApprovalQueue,
    *,
    tenant_id: str,
    agent: str,
    user_id: str,
    action: str,
    payload: dict,
) -> ApprovalRequest:
    req = ApprovalRequest(
        tenant_id=tenant_id,
        requested_by_agent=agent,
        requested_for_user=user_id,
        action=action,
        payload=payload,
        created_at=datetime.now(UTC),
    )
    return await queue.enqueue(req)

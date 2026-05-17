"""GET  /tenants/{id}/approvals — pending approvals for the tenant.
POST /tenants/{id}/approvals/{request_id}/decide — approve or deny."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from avengers.api.app import AppContainer
from avengers.api.deps import get_container, require_tenant_ctx
from avengers.core.tenant import TenantContext

router = APIRouter(prefix="/tenants/{tenant_id}/approvals", tags=["approvals"])


class DecideRequest(BaseModel):
    decision: Literal["approved", "denied"]
    reason: str | None = Field(default=None, max_length=500)


@router.get("")
async def list_pending(
    ctx: Annotated[TenantContext, Depends(require_tenant_ctx)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> list[dict]:
    items = await container.approvals.list_pending(ctx.tenant_id)
    return [it.model_dump(mode="json") for it in items]


@router.post("/{request_id}/decide")
async def decide(
    request_id: UUID,
    body: DecideRequest,
    ctx: Annotated[TenantContext, Depends(require_tenant_ctx)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict:
    assert ctx.user is not None
    try:
        updated = await container.approvals.decide(
            request_id,
            decided_by=ctx.user.id,
            decision=body.decision,
            reason=body.reason,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if updated.tenant_id != ctx.tenant_id:
        # Belt-and-braces: someone guessed a UUID for another tenant.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="cross-tenant approval")
    await container.auditor.emit(
        tenant_id=ctx.tenant_id,
        actor=f"user:{ctx.user.id}",
        kind="approval.decided",
        target=str(request_id),
        payload={"decision": body.decision, "reason": body.reason},
        severity="warn",
    )
    return updated.model_dump(mode="json")

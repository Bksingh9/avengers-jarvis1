"""Admin-only endpoints — config reload, budget snapshots, kill switch ops."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from avengers.api.app import AppContainer
from avengers.api.deps import get_container, require_admin_ctx
from avengers.core.tenant import TenantContext

router = APIRouter(prefix="/tenants/{tenant_id}/admin", tags=["admin"])


@router.post("/config/reload")
async def reload_config(
    _ctx: Annotated[TenantContext, Depends(require_admin_ctx)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict:
    container.config_store.reload()
    return {
        "ok": True,
        "tenants": len(container.config_store.all_tenants()),
        "agents": len(container.config_store.all_agents()),
        "policies": len(container.config_store.policies()),
    }


@router.get("/budget")
async def budget_snapshot(
    ctx: Annotated[TenantContext, Depends(require_admin_ctx)],
    container: Annotated[AppContainer, Depends(get_container)],
    for_date: date | None = None,
) -> dict:
    if container.budget is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="budget tracker not wired"
        )
    snap = await container.budget.snapshot(ctx.tenant_id, for_date=for_date)
    return {
        "tenant_id": snap.tenant_id,
        "for_date": snap.for_date.isoformat(),
        "tenant_spend_usd": snap.tenant_spend_usd,
        "per_user_spend_usd": snap.per_user_spend_usd,
    }

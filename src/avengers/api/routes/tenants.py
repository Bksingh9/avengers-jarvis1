"""GET /tenants/{tenant_id} — minimal tenant lookup."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from avengers.api.deps import require_tenant_ctx
from avengers.core.tenant import TenantContext

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.get("/{tenant_id}")
async def get_tenant(ctx: Annotated[TenantContext, Depends(require_tenant_ctx)]) -> dict:
    t = ctx.tenant
    return {
        "id": t.id,
        "name": t.name,
        "region": t.region,
        "timezone": t.timezone,
        "agents_enabled": t.agents_enabled,
        "budgets": t.budgets.model_dump(),
    }

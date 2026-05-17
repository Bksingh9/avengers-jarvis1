"""GET /tenants/{id}/users/me — return the authenticated user."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from avengers.api.deps import require_tenant_ctx
from avengers.core.tenant import TenantContext

router = APIRouter(prefix="/tenants/{tenant_id}/users", tags=["users"])


@router.get("/me")
async def me(ctx: Annotated[TenantContext, Depends(require_tenant_ctx)]) -> dict:
    u = ctx.user
    assert u is not None
    return {
        "id": u.id,
        "email": u.email,
        "display_name": u.display_name,
        "tenant_id": u.tenant_id,
        "groups": sorted(u.groups),
        "timezone": u.timezone,
        "delivery_prefs": u.delivery_prefs.model_dump(),
    }

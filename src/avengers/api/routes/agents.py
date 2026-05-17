"""GET /tenants/{id}/agents — list configured agents for the tenant."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from avengers.api.app import AppContainer
from avengers.api.deps import get_container, require_tenant_ctx
from avengers.core.tenant import TenantContext

router = APIRouter(prefix="/tenants/{tenant_id}/agents", tags=["agents"])


@router.get("")
async def list_agents(
    ctx: Annotated[TenantContext, Depends(require_tenant_ctx)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> list[dict]:
    enabled = set(ctx.tenant.agents_enabled)
    out: list[dict] = []
    for a in container.config_store.all_agents():
        if a.id not in enabled:
            continue
        out.append(
            {
                "id": a.id,
                "display_name": a.display_name,
                "version": a.version,
                "model": a.model.primary,
                "policies": a.policies,
            }
        )
    return out


@router.get("/{agent_id}")
async def get_agent(
    agent_id: str,
    ctx: Annotated[TenantContext, Depends(require_tenant_ctx)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict:
    if agent_id not in ctx.tenant.agents_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="agent not enabled")
    try:
        cfg = container.config_store.agent(agent_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown agent") from exc
    return cfg.model_dump()

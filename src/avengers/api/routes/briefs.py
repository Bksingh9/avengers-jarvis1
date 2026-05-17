"""POST /tenants/{id}/briefs — trigger a morning brief now.
GET  /tenants/{id}/briefs/{for_date} — fetch a previously generated brief.

In v1 the in-process `last_briefs` map keys briefs by (tenant, user, date).
Production swaps in a Postgres-backed brief store.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from avengers.api.app import AppContainer
from avengers.api.deps import get_container, require_tenant_ctx
from avengers.core.tenant import TenantContext
from avengers.workflows.morning_brief import run_morning_brief

router = APIRouter(prefix="/tenants/{tenant_id}/briefs", tags=["briefs"])


class TriggerBriefRequest(BaseModel):
    for_date: date | None = None


@router.post("", status_code=status.HTTP_201_CREATED)
async def trigger(
    body: TriggerBriefRequest,
    ctx: Annotated[TenantContext, Depends(require_tenant_ctx)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict:
    assert ctx.user is not None
    target_date = body.for_date or date.today()
    brief = await run_morning_brief(
        user=ctx.user,
        for_date=target_date,
        ctx=ctx,
        director=container.director,
        memory=container.memory,
        auditor=container.auditor,
        channels=container.delivery_channels,
    )
    container.last_briefs[(ctx.tenant_id, ctx.user.id, target_date.isoformat())] = brief
    return {
        "id": str(brief.id),
        "for_date": brief.for_date.isoformat(),
        "sections": [
            {"agent": s.agent, "status": s.status, "latency_ms": s.latency_ms, "cost_usd": s.cost_usd}
            for s in brief.sections
        ],
        "total_cost_usd": brief.total_cost_usd,
    }


@router.get("/{for_date}")
async def fetch(
    for_date: date,
    ctx: Annotated[TenantContext, Depends(require_tenant_ctx)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict:
    assert ctx.user is not None
    key = (ctx.tenant_id, ctx.user.id, for_date.isoformat())
    if key not in container.last_briefs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no brief for that date")
    return container.last_briefs[key].model_dump(mode="json")

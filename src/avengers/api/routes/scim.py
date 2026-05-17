"""Minimal SCIM 2.0 ingress (spec §12.1).

Provider posts user/group create/update/delete events here; we translate to
`SCIMEvent` and hand off to the bound `IdentityProvider`. Real implementations
need full SCIM 2.0 conformance — this v1 surface is the protocol shim.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field

from avengers.api.app import AppContainer
from avengers.api.deps import get_container, require_admin_ctx
from avengers.core.tenant import TenantContext
from avengers.identity.base import SCIMEvent

router = APIRouter(prefix="/tenants/{tenant_id}/scim/v2", tags=["scim"])


class SCIMUserPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    op: Literal["create", "update", "delete"]
    user: dict = Field(default_factory=dict)


@router.post("/users", status_code=status.HTTP_202_ACCEPTED)
async def post_user_event(
    body: SCIMUserPayload,
    _ctx: Annotated[TenantContext, Depends(require_admin_ctx)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict:
    event = SCIMEvent(
        op=body.op,
        resource="user",
        id=body.id,
        data=body.user,
        ts=datetime.now(UTC),
    )
    await container.identity.on_scim_event(event)
    return {"accepted": True, "id": body.id, "op": body.op}

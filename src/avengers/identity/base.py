"""Identity-provider Protocol (spec §9.3)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

from avengers.schemas.identity import Tenant, User


class SCIMEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["create", "update", "delete"]
    resource: Literal["user", "group"]
    id: str
    data: dict
    ts: datetime


class IdentityProvider(Protocol):
    async def verify_token(self, jwt: str) -> User: ...

    async def list_users(self, tenant: Tenant) -> list[User]: ...

    async def resolve_groups(self, user_id: str) -> set[str]: ...

    async def on_scim_event(self, event: SCIMEvent) -> None: ...

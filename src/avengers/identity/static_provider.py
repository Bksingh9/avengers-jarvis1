"""Static identity provider for tests and offline single-tenant installs.

Users are seeded at construction. `verify_token` accepts `user:<id>` tokens.
Production should plug in the OIDC or SAML adapter.
"""

from __future__ import annotations

from avengers.identity.base import IdentityProvider, SCIMEvent
from avengers.schemas.identity import Tenant, User


class StaticIdentityProvider(IdentityProvider):
    def __init__(self, users: list[User]) -> None:
        self._users: dict[str, User] = {u.id: u for u in users}

    async def verify_token(self, jwt: str) -> User:
        if not jwt.startswith("user:"):
            raise PermissionError("invalid token")
        uid = jwt[len("user:"):]
        if uid not in self._users:
            raise PermissionError(f"unknown user: {uid}")
        return self._users[uid]

    async def list_users(self, tenant: Tenant) -> list[User]:
        return [u for u in self._users.values() if u.tenant_id == tenant.id]

    async def resolve_groups(self, user_id: str) -> set[str]:
        u = self._users.get(user_id)
        return set(u.groups) if u else set()

    async def on_scim_event(self, event: SCIMEvent) -> None:
        if event.resource != "user":
            return
        if event.op == "delete":
            self._users.pop(event.id, None)
            return
        if event.op == "create":
            self._users[event.id] = User.model_validate(event.data)
        elif event.op == "update":
            cur = self._users.get(event.id)
            if cur is None:
                return
            self._users[event.id] = cur.model_copy(update=event.data)

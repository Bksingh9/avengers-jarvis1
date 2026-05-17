"""OIDC identity provider (spec §12.1).

Validates a bearer access token by calling the IdP's userinfo endpoint and
maps the resulting claims into a `User`. Production deployments should swap
in local JWT verification (PyJWT + JWKS cache) for performance and to remove
the per-request round-trip — but using userinfo keeps this adapter dependency-
light and correct by default.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from avengers.identity.base import IdentityProvider, SCIMEvent
from avengers.schemas.identity import DeliveryPrefs, Tenant, User

logger = logging.getLogger(__name__)


class OIDCProvider(IdentityProvider):
    def __init__(
        self,
        *,
        issuer: str,
        tenant_id: str,
        group_claim: str = "groups",
        timezone_claim: str = "zoneinfo",
        userinfo_url: str | None = None,
        http: httpx.AsyncClient | None = None,
        admin_group: str = "avengers-admin",
    ) -> None:
        self._issuer = issuer.rstrip("/")
        self._tenant_id = tenant_id
        self._group_claim = group_claim
        self._tz_claim = timezone_claim
        self._userinfo_url = userinfo_url
        self._http = http or httpx.AsyncClient(timeout=5.0)
        self._admin_group = admin_group
        self._discovery: dict[str, Any] | None = None
        self._user_cache: dict[str, User] = {}

    async def _discover(self) -> dict[str, Any]:
        if self._discovery is not None:
            return self._discovery
        url = f"{self._issuer}/.well-known/openid-configuration"
        resp = await self._http.get(url)
        resp.raise_for_status()
        self._discovery = resp.json()
        return self._discovery

    async def _userinfo(self, token: str) -> dict[str, Any]:
        url = self._userinfo_url
        if url is None:
            disc = await self._discover()
            url = disc["userinfo_endpoint"]
        resp = await self._http.get(url, headers={"Authorization": f"Bearer {token}"})
        if resp.status_code == 401:
            raise PermissionError("token rejected by IdP")
        resp.raise_for_status()
        return resp.json()

    # ---- IdentityProvider --------------------------------------------------

    async def verify_token(self, jwt: str) -> User:
        if jwt in self._user_cache:
            return self._user_cache[jwt]
        try:
            claims = await self._userinfo(jwt)
        except PermissionError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise PermissionError(f"OIDC verification failed: {exc}") from exc

        sub = claims.get("sub")
        email = claims.get("email")
        if not sub or not email:
            raise PermissionError("missing sub/email claim")
        groups_raw = claims.get(self._group_claim, [])
        groups = set(groups_raw) if isinstance(groups_raw, list) else {str(groups_raw)}
        user = User(
            id=sub,
            tenant_id=self._tenant_id,
            email=email,
            display_name=claims.get("name") or email,
            groups=groups,
            timezone=claims.get(self._tz_claim, "UTC"),
            delivery_prefs=DeliveryPrefs(),
        )
        self._user_cache[jwt] = user
        return user

    async def list_users(self, tenant: Tenant) -> list[User]:
        # SCIM is the source of truth for membership; userinfo is per-token.
        # Production binds a SCIM-store-backed implementation.
        return list(self._user_cache.values())

    async def resolve_groups(self, user_id: str) -> set[str]:
        for u in self._user_cache.values():
            if u.id == user_id:
                return set(u.groups)
        return set()

    async def on_scim_event(self, event: SCIMEvent) -> None:
        # OIDC adapter doesn't own SCIM state; the SCIM ingest is wired to a
        # different store. We just invalidate any cached entries we'd have.
        if event.resource == "user" and event.op == "delete":
            self._user_cache = {k: v for k, v in self._user_cache.items() if v.id != event.id}

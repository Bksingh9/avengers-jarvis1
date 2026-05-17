"""OIDC adapter — uses an in-process httpx MockTransport to stub the IdP."""

from __future__ import annotations

import httpx
import pytest

from avengers.identity.oidc import OIDCProvider


def _idp_transport(*, userinfo_status: int = 200, groups_claim: str = "groups"):
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/.well-known/openid-configuration"):
            return httpx.Response(
                200,
                json={"userinfo_endpoint": "https://idp.example.com/userinfo"},
            )
        if req.url.path == "/userinfo":
            assert req.headers["Authorization"].startswith("Bearer ")
            if userinfo_status != 200:
                return httpx.Response(userinfo_status, json={"error": "denied"})
            return httpx.Response(
                200,
                json={
                    "sub": "alice",
                    "email": "alice@acme.com",
                    "name": "Alice",
                    groups_claim: ["avengers-admin", "research-readers"],
                    "zoneinfo": "Asia/Kolkata",
                },
            )
        return httpx.Response(404)

    return httpx.MockTransport(handler)


@pytest.fixture
def http_client():
    return httpx.AsyncClient(transport=_idp_transport())


@pytest.fixture
def http_client_401():
    return httpx.AsyncClient(transport=_idp_transport(userinfo_status=401))


async def test_verify_token_maps_claims(http_client: httpx.AsyncClient):
    idp = OIDCProvider(
        issuer="https://idp.example.com",
        tenant_id="acme",
        http=http_client,
    )
    user = await idp.verify_token("opaque-access-token")
    assert user.id == "alice"
    assert user.tenant_id == "acme"
    assert user.email == "alice@acme.com"
    assert user.timezone == "Asia/Kolkata"
    assert {"avengers-admin", "research-readers"} <= user.groups


async def test_verify_token_caches(http_client: httpx.AsyncClient):
    idp = OIDCProvider(
        issuer="https://idp.example.com",
        tenant_id="acme",
        http=http_client,
    )
    u1 = await idp.verify_token("token-x")
    u2 = await idp.verify_token("token-x")
    assert u1 is u2  # cached identity


async def test_userinfo_401_raises_permission(http_client_401: httpx.AsyncClient):
    idp = OIDCProvider(
        issuer="https://idp.example.com",
        tenant_id="acme",
        http=http_client_401,
    )
    with pytest.raises(PermissionError):
        await idp.verify_token("bad-token")


async def test_custom_group_claim():
    transport = _idp_transport(groups_claim="roles")
    async with httpx.AsyncClient(transport=transport) as http:
        idp = OIDCProvider(
            issuer="https://idp.example.com",
            tenant_id="acme",
            group_claim="roles",
            http=http,
        )
        # With group_claim=roles the standard `groups` claim should be empty
        user = await idp.verify_token("t")
    assert user.groups == {"avengers-admin", "research-readers"}

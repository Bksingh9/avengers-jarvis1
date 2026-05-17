from datetime import UTC, datetime

import pytest

from avengers.identity.base import SCIMEvent
from avengers.identity.static_provider import StaticIdentityProvider
from avengers.schemas.identity import Tenant, User


def _u(uid: str, tid: str = "acme", groups: set[str] | None = None) -> User:
    return User(
        id=uid,
        tenant_id=tid,
        email=f"{uid}@example.com",
        display_name=uid,
        groups=groups or set(),
        timezone="UTC",
    )


async def test_verify_and_list():
    idp = StaticIdentityProvider([_u("a"), _u("b"), _u("c", tid="other")])
    u = await idp.verify_token("user:a")
    assert u.id == "a"
    tenant = Tenant(id="acme", name="ACME", region="us", timezone="UTC", locale="en")
    assert {u.id for u in await idp.list_users(tenant)} == {"a", "b"}


async def test_unknown_token_rejected():
    idp = StaticIdentityProvider([_u("a")])
    with pytest.raises(PermissionError):
        await idp.verify_token("user:bogus")
    with pytest.raises(PermissionError):
        await idp.verify_token("bearer xyz")


async def test_scim_create_and_delete():
    idp = StaticIdentityProvider([])
    await idp.on_scim_event(
        SCIMEvent(
            op="create",
            resource="user",
            id="z",
            data={
                "id": "z",
                "tenant_id": "acme",
                "email": "z@example.com",
                "display_name": "Z",
                "groups": ["g1"],
                "timezone": "UTC",
            },
            ts=datetime.now(UTC),
        )
    )
    assert (await idp.verify_token("user:z")).groups == {"g1"}
    await idp.on_scim_event(
        SCIMEvent(op="delete", resource="user", id="z", data={}, ts=datetime.now(UTC))
    )
    with pytest.raises(PermissionError):
        await idp.verify_token("user:z")

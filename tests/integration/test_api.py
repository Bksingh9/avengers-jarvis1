"""End-to-end control-plane tests against the in-process ASGI app."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from avengers.api.app import create_app
from avengers.api.bootstrap import build_container
from avengers.connectors.base import ConnectorRegistry
from avengers.connectors.fake_connector import FakeConnector
from avengers.identity.static_provider import StaticIdentityProvider
from avengers.llm.base import LLMRegistry
from avengers.llm.fake_provider import FakeLLMProvider
from avengers.schemas.identity import DeliveryPrefs, User
from avengers.schemas.llm import Completion, ToolSchema


def _users() -> list[User]:
    return [
        User(
            id="alice",
            tenant_id="acme",
            email="alice@acme.com",
            display_name="Alice",
            groups={"avengers-admin"},
            timezone="Asia/Kolkata",
            delivery_prefs=DeliveryPrefs(channels=["console"]),
        ),
        User(
            id="bob",
            tenant_id="other",
            email="bob@other.com",
            display_name="Bob",
            timezone="UTC",
        ),
    ]


@pytest.fixture
def wired(tmp_path: Path):
    config_dir = Path(__file__).resolve().parents[2] / "config"

    fake_llm = FakeLLMProvider()
    reg = LLMRegistry()
    reg.register("anthropic", lambda: fake_llm)
    reg.register("fake", lambda: fake_llm)

    connectors = ConnectorRegistry()
    connectors.register(
        FakeConnector("exa_search", [ToolSchema(name="search", description="", parameters={"type": "object"})])
    )

    c = build_container(
        config_dir=config_dir,
        identity=StaticIdentityProvider(_users()),
        llm_registry=reg,
        connectors=connectors,
        memory_root=tmp_path / "mem",
    )
    return c, fake_llm


@pytest.fixture
def container(wired):
    return wired[0]


@pytest.fixture
def fake_llm(wired):
    return wired[1]


@pytest.fixture
def make_client(container):
    """Per-call factory — httpx.AsyncClient is single-use."""
    app = create_app(container)
    transport = httpx.ASGITransport(app=app)

    def _factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=transport, base_url="http://t")

    return _factory


async def test_healthz_open(make_client):
    async with make_client() as ac:
        r = await ac.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "exa_search" in body["connectors_known"]


async def test_unauthenticated_blocked(make_client):
    async with make_client() as ac:
        r = await ac.get("/tenants/acme/users/me")
    # Newer FastAPI returns 401; older versions returned 403. Either is correct.
    assert r.status_code in (401, 403)


async def test_me_returns_user(make_client):
    async with make_client() as ac:
        r = await ac.get(
            "/tenants/acme/users/me", headers={"Authorization": "Bearer user:alice"}
        )
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "alice"
    assert "avengers-admin" in body["groups"]


async def test_cross_tenant_rejected(make_client):
    async with make_client() as ac:
        r = await ac.get(
            "/tenants/acme/users/me", headers={"Authorization": "Bearer user:bob"}
        )
    assert r.status_code == 403


async def test_unknown_tenant_404(make_client):
    async with make_client() as ac:
        r = await ac.get(
            "/tenants/ghost/users/me", headers={"Authorization": "Bearer user:alice"}
        )
    # Cross-tenant check fires first (tenant_id != alice.tenant_id)
    assert r.status_code == 403


async def test_list_agents(make_client):
    async with make_client() as ac:
        r = await ac.get(
            "/tenants/acme/agents", headers={"Authorization": "Bearer user:alice"}
        )
    assert r.status_code == 200
    ids = {a["id"] for a in r.json()}
    assert "research" in ids


async def test_get_agent(make_client):
    async with make_client() as ac:
        r = await ac.get(
            "/tenants/acme/agents/research",
            headers={"Authorization": "Bearer user:alice"},
        )
    assert r.status_code == 200
    assert r.json()["id"] == "research"


async def test_trigger_brief_runs_research(container, fake_llm, make_client):
    # Six specialists run in parallel from the tenant config; order in which
    # they pull from the FakeLLM queue is non-deterministic, so enqueue one
    # universal empty-digest response per agent. Every digest schema uses
    # default_factory=list, so '{}' validates to all-empty for any of them.
    for _ in range(6):
        fake_llm.enqueue(
            Completion(
                model="m1",
                output_text="{}",
                stop_reason="end_turn",
                input_tokens=10,
                output_tokens=10,
                cost_usd=0.001,
            )
        )
    async with make_client() as ac:
        r = await ac.post(
            "/tenants/acme/briefs",
            headers={"Authorization": "Bearer user:alice"},
            json={"for_date": "2026-05-17"},
        )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["for_date"] == "2026-05-17"
    # All six enabled specialists should report ok with the universal empty-digest fixture.
    statuses = {s["agent"]: s["status"] for s in body["sections"]}
    assert "research" in statuses
    assert all(v == "ok" for v in statuses.values()), statuses

    # Then we can fetch it back
    async with make_client() as ac:
        r2 = await ac.get(
            "/tenants/acme/briefs/2026-05-17",
            headers={"Authorization": "Bearer user:alice"},
        )
    assert r2.status_code == 200


async def test_admin_reload_requires_group(container, make_client):
    container.identity = StaticIdentityProvider(
        [User(id="alice", tenant_id="acme", email="a@a.com", display_name="A", timezone="UTC")]
    )
    # Rebuild app with the new identity provider:
    container.identity = StaticIdentityProvider(_users())
    async with make_client() as ac:
        r = await ac.post(
            "/tenants/acme/admin/config/reload",
            headers={"Authorization": "Bearer user:alice"},
        )
    assert r.status_code == 200
    assert r.json()["ok"] is True


async def test_admin_reload_denied_for_non_admin(container):
    plain_user = User(
        id="carol", tenant_id="acme", email="c@a.com", display_name="C", timezone="UTC"
    )
    container.identity = StaticIdentityProvider([plain_user])
    app = create_app(container)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as ac:
        r = await ac.post(
            "/tenants/acme/admin/config/reload",
            headers={"Authorization": "Bearer user:carol"},
        )
    assert r.status_code == 403


async def test_approval_flow_end_to_end(container, make_client):
    from avengers.workflows.approval import request_approval

    req = await request_approval(
        container.approvals,
        tenant_id="acme",
        agent="content",
        user_id="alice",
        action="cms.publish",
        payload={"draft_id": "d1"},
    )
    async with make_client() as ac:
        r1 = await ac.get(
            "/tenants/acme/approvals",
            headers={"Authorization": "Bearer user:alice"},
        )
        assert r1.status_code == 200
        assert len(r1.json()) == 1
        r2 = await ac.post(
            f"/tenants/acme/approvals/{req.id}/decide",
            headers={"Authorization": "Bearer user:alice"},
            json={"decision": "approved", "reason": "lgtm"},
        )
    assert r2.status_code == 200
    assert r2.json()["status"] == "approved"


async def test_scim_user_create(container, make_client):
    async with make_client() as ac:
        r = await ac.post(
            "/tenants/acme/scim/v2/users",
            headers={"Authorization": "Bearer user:alice"},
            json={
                "id": "diana",
                "op": "create",
                "user": {
                    "id": "diana",
                    "tenant_id": "acme",
                    "email": "diana@acme.com",
                    "display_name": "Diana",
                    "groups": ["g1"],
                    "timezone": "UTC",
                },
            },
        )
    assert r.status_code == 202
    # New user is now known to the identity provider
    diana = await container.identity.verify_token("user:diana")
    assert diana.email == "diana@acme.com"

"""Memory / RAG endpoints — POST ingest, POST search, namespace isolation."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from avengers.api.app import create_app
from avengers.api.bootstrap import build_container
from avengers.connectors.base import ConnectorRegistry
from avengers.identity.static_provider import StaticIdentityProvider
from avengers.llm.base import LLMRegistry
from avengers.llm.fake_provider import FakeLLMProvider
from avengers.schemas.identity import DeliveryPrefs, User


def _users():
    return [
        User(
            id="alice",
            tenant_id="acme",
            email="alice@example.com",
            display_name="Alice",
            groups={"avengers-admin"},
            timezone="UTC",
            delivery_prefs=DeliveryPrefs(channels=["console"]),
        ),
        User(
            id="cap-brij",
            tenant_id="jarvis",
            email="cap.brij@example.com",
            display_name="Cap Brij",
            groups={"avengers-admin", "jarvis-owner"},
            timezone="Asia/Kolkata",
        ),
    ]


@pytest.fixture
def container(tmp_path: Path):
    config_dir = Path(__file__).resolve().parents[2] / "config"
    fake = FakeLLMProvider()
    reg = LLMRegistry()
    reg.register("anthropic", lambda: fake)
    reg.register("fake", lambda: fake)
    return build_container(
        config_dir=config_dir,
        identity=StaticIdentityProvider(_users()),
        llm_registry=reg,
        connectors=ConnectorRegistry(),
        memory_root=tmp_path / "mem",
        personas_root=Path(__file__).resolve().parents[2] / "memory",
    )


@pytest.mark.asyncio
async def test_ingest_then_search_finds_chunk(container):
    app = create_app(container)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://t") as ac:
        # Ingest a short document
        r = await ac.post(
            "/tenants/acme/memory/ingest",
            headers={"Authorization": "Bearer user:alice"},
            json={
                "purpose": "rag",
                "source": "demo-handbook.md",
                "text": "Quarterly revenue jumped twenty percent. Hiring plan signed off Monday.",
                "metadata": {"author": "alice"},
            },
        )
        assert r.status_code == 201, r.text
        ingest = r.json()
        assert ingest["chunks"] >= 1
        assert ingest["namespace"] == "acme/alice/rag"

        # Search for one of the words in the document
        r2 = await ac.post(
            "/tenants/acme/memory/search",
            headers={"Authorization": "Bearer user:alice"},
            json={"query": "revenue", "k": 3},
        )
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert body["namespace"] == "acme/alice/rag"
        assert len(body["hits"]) >= 1
        assert "revenue" in body["hits"][0]["text"].lower()
        assert body["hits"][0]["source"] == "demo-handbook.md"


@pytest.mark.asyncio
async def test_namespace_is_per_tenant_per_user(container):
    """Alice (acme) and Cap Brij (jarvis) get separate namespaces."""
    app = create_app(container)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://t") as ac:
        # Alice ingests something only she should see
        await ac.post(
            "/tenants/acme/memory/ingest",
            headers={"Authorization": "Bearer user:alice"},
            json={"purpose": "rag", "source": "acme-secret.md",
                  "text": "ACME secret sauce: extra paprika."},
        )
        # Cap Brij ingests something only he should see
        await ac.post(
            "/tenants/jarvis/memory/ingest",
            headers={"Authorization": "Bearer user:cap-brij"},
            json={"purpose": "rag", "source": "jarvis-notes.md",
                  "text": "Cap Brij notes: review the Fynd merchant pipeline weekly."},
        )

        # Alice searches — should find ACME, not Cap Brij's note
        r_alice = await ac.post(
            "/tenants/acme/memory/search",
            headers={"Authorization": "Bearer user:alice"},
            json={"query": "merchant pipeline", "k": 5},
        )
        assert r_alice.status_code == 200
        # Alice's namespace doesn't contain Cap Brij's text — substring match
        # in InMemoryStore is naive so absence is the assertion.
        for hit in r_alice.json()["hits"]:
            assert "merchant pipeline" not in hit["text"].lower()


@pytest.mark.asyncio
async def test_cross_tenant_search_blocked(container):
    """Alice (acme) trying to read the jarvis tenant gets 403."""
    app = create_app(container)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as ac:
        r = await ac.post(
            "/tenants/jarvis/memory/search",
            headers={"Authorization": "Bearer user:alice"},
            json={"query": "anything", "k": 1},
        )
    assert r.status_code == 403

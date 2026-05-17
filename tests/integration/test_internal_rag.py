"""Internal RAG connector — auto-registered, MCP-shaped, queryable by agents."""

from __future__ import annotations

from pathlib import Path

import pytest

from avengers.api.bootstrap import build_container
from avengers.connectors.base import ConnectorRegistry, ToolInvocation
from avengers.core.tenant import TenantContext
from avengers.identity.static_provider import StaticIdentityProvider
from avengers.llm.base import LLMRegistry
from avengers.llm.fake_provider import FakeLLMProvider
from avengers.memory.base import MemoryItem
from avengers.schemas.identity import User


def _user() -> User:
    return User(
        id="alice",
        tenant_id="acme",
        email="alice@example.com",
        display_name="Alice",
        groups={"avengers-admin"},
        timezone="UTC",
    )


@pytest.fixture
def container(tmp_path: Path):
    config_dir = Path(__file__).resolve().parents[2] / "config"
    fake = FakeLLMProvider()
    reg = LLMRegistry()
    reg.register("anthropic", lambda: fake)
    return build_container(
        config_dir=config_dir,
        identity=StaticIdentityProvider([_user()]),
        llm_registry=reg,
        connectors=ConnectorRegistry(),
        memory_root=tmp_path / "fs",
        personas_root=Path(__file__).resolve().parents[2] / "memory",
    )


def test_internal_rag_is_auto_registered(container):
    """build_container should always register internal_rag, even when the
    caller passes a fresh ConnectorRegistry()."""
    assert "internal_rag" in container.connectors.known()


@pytest.mark.asyncio
async def test_internal_rag_search_finds_ingested_docs(container):
    """Round-trip: ingest a doc via the vector store, then call
    internal_rag.search through the connector exactly like an agent would."""
    ns = "acme/alice/rag"
    await container.vector_memory.upsert(ns, [
        MemoryItem(
            id="handbook-1",
            text="RTO threshold per region is 5 percent. Anything higher triggers a courier review.",
            metadata={"source": "ops-handbook.md", "chunk_idx": 0},
        ),
        MemoryItem(
            id="handbook-2",
            text="Settlement reconciliation runs every Friday at 11 PM IST.",
            metadata={"source": "ops-handbook.md", "chunk_idx": 1},
        ),
    ])

    client = container.connectors.get("internal_rag")
    ctx = TenantContext(
        tenant=container.config_store.tenant("acme"),
        user=_user(),
    )
    result = await client.invoke(ToolInvocation(tool="search", args={"query": "RTO threshold", "k": 3}), ctx)

    assert result.ok, result.error
    out = result.output
    assert out["namespace"] == ns
    assert len(out["hits"]) >= 1
    top = out["hits"][0]
    assert "RTO threshold" in top["text"]
    assert top["source"] == "ops-handbook.md"


@pytest.mark.asyncio
async def test_internal_rag_namespace_is_per_tenant_user(container):
    """A user in tenant A cannot retrieve docs from tenant B."""
    ns_acme = "acme/alice/rag"
    ns_other = "other-tenant/bob/rag"

    await container.vector_memory.upsert(ns_acme, [
        MemoryItem(id="x", text="ACME-only fact", metadata={"source": "a.md"}),
    ])
    await container.vector_memory.upsert(ns_other, [
        MemoryItem(id="y", text="Other-tenant fact", metadata={"source": "b.md"}),
    ])

    client = container.connectors.get("internal_rag")
    ctx_acme = TenantContext(
        tenant=container.config_store.tenant("acme"),
        user=_user(),
    )
    r = await client.invoke(ToolInvocation(tool="search", args={"query": "fact"}), ctx_acme)
    texts = " ".join(h["text"] for h in r.output["hits"])
    assert "ACME-only fact" in texts
    assert "Other-tenant fact" not in texts


@pytest.mark.asyncio
async def test_research_agent_can_now_see_internal_rag(container):
    """The research agent's `_collect_tools()` should now include internal_rag
    because the config lists it AND the connector is registered."""
    agent = container.director.specialists["research"]
    tools, _index = await agent._collect_tools()
    tool_names = {t.name for t in tools}
    assert "internal_rag.search" in tool_names
    assert "internal_rag.list_recent" in tool_names

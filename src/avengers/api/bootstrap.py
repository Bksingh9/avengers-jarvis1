"""Compose an `AppContainer` for tests or simple single-process deployments.

Production wires this up in `__main__.py`; tests use this helper to build a
fake-backed container in two lines.
"""

from __future__ import annotations

from pathlib import Path

from avengers.agents.base import AgentDeps
from avengers.agents.catalog import CatalogAgent
from avengers.agents.content import ContentAgent
from avengers.agents.director import Director
from avengers.agents.inventory import InventoryAgent
from avengers.agents.markets import MarketsAgent
from avengers.agents.meetings import MeetingsAgent
from avengers.agents.operations import OperationsAgent
from avengers.agents.reconciliation import ReconciliationAgent
from avengers.agents.research import ResearchAgent
from avengers.agents.security import SecurityAgent
from avengers.api.app import AppContainer
from avengers.connectors.base import ConnectorRegistry
from avengers.connectors.internal_rag import InternalRAGConnector
from avengers.core.audit import Auditor, InMemoryAuditSink
from avengers.core.budget import BudgetTracker
from avengers.core.config_loader import ConfigStore
from avengers.core.policy import PolicyEngine
from avengers.delivery.console_channel import ConsoleChannel
from avengers.identity.base import IdentityProvider
from avengers.llm.base import LLMRegistry
from avengers.llm.router import LLMRouter
from avengers.memory.base import MemoryStore
from avengers.memory.fs_memory import FilesystemMemory
from avengers.memory.in_memory_store import InMemoryStore
from avengers.workflows.approval import ApprovalQueue


_SPECIALIST_CLASSES = {
    "meetings": MeetingsAgent,
    "markets": MarketsAgent,
    "security": SecurityAgent,
    "research": ResearchAgent,
    "content": ContentAgent,
    "operations": OperationsAgent,
    # Fynd-specific (BRD §9.2)
    "catalog": CatalogAgent,
    "inventory": InventoryAgent,
    "reconciliation": ReconciliationAgent,
}


def build_container(
    *,
    config_dir: Path,
    identity: IdentityProvider,
    llm_registry: LLMRegistry,
    connectors: ConnectorRegistry,
    memory_root: Path | None = None,
    auditor: Auditor | None = None,
    personas_root: Path | None = None,
    vector_memory: MemoryStore | None = None,
) -> AppContainer:
    store = ConfigStore(config_dir)
    store.reload()

    auditor = auditor or Auditor(InMemoryAuditSink())
    policies = PolicyEngine(store.policies())
    router = LLMRouter(registry=llm_registry)

    # Optional per-tenant persona overlay. Files at
    # `<personas_root>/<tenant_id>/persona.md` are loaded as
    # `system_prompts["persona:<tenant_id>"]` and prepended to every agent
    # prompt run for that tenant. This is how JARVIS gets its "Cap Brij"
    # voice on top of the same six reference specialists ACME uses.
    system_prompts: dict[str, str] = {}
    if personas_root and personas_root.exists():
        for persona_file in personas_root.glob("*/persona.md"):
            tenant_id = persona_file.parent.name
            system_prompts[f"persona:{tenant_id}"] = persona_file.read_text()

    deps = AgentDeps(
        router=router,
        connectors=connectors,
        policies=policies,
        auditor=auditor,
        budget=BudgetTracker(),
        system_prompts=system_prompts,
    )

    memory = FilesystemMemory(memory_root) if memory_root else None
    # Default the vector store to in-process so /memory/ingest works out of
    # the box. Production wires PgVectorStore / TurbopufferStore / Pinecone.
    vector_memory = vector_memory or InMemoryStore()

    # Auto-register the internal_rag connector against the vector store.
    # Any agent that lists `internal_rag` in its tools.mcp config now gets
    # a `search` tool — that's the LangChain-style retrieval pattern wired
    # into the existing typed agent loop. Specialists collect tools lazily
    # at run() time, so we don't need to instantiate them before this point.
    if "internal_rag" not in connectors.known():
        connectors.register(InternalRAGConnector(vector_memory))

    specialists = {}
    for agent_cfg in store.all_agents():
        cls = _SPECIALIST_CLASSES.get(agent_cfg.id)
        if cls is None:
            continue
        specialists[agent_cfg.id] = cls(agent_cfg, deps)

    director = Director(deps=deps, specialists=specialists)

    return AppContainer(
        config_store=store,
        identity=identity,
        router=router,
        connectors=connectors,
        policies=policies,
        auditor=auditor,
        approvals=ApprovalQueue(),
        director=director,
        delivery_channels={"console": ConsoleChannel()},
        budget=deps.budget,
        memory=memory,
        vector_memory=vector_memory,
    )

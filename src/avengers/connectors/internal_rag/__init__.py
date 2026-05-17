"""Internal RAG connector — exposes the tenant's vector memory as MCP tools.

Wraps `MemoryStore.search` (and friends) so any specialist that lists
`internal_rag` in its `tools.mcp` config can cite documents the user has
ingested via `POST /memory/ingest`.

This is the LangChain-equivalent "retrieval tool" pattern, plugged into the
existing typed agent loop. Critically: the namespace is derived from the
caller's `TenantContext` — agents can never query another tenant's documents,
even if they ask for it by name.

Tools exposed:
  * `search(query, k=5, purpose="rag")` — top-k similarity hits with text + source
  * `list_recent(purpose, limit)`       — recently ingested items (for debugging)

Cited-claim contract: every result includes a `source` field that the agent
can pass through into the `Cited.sources` array, so the cite_every_claim
policy stays green.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from avengers.connectors.base import (
    ConnectorClient,
    ConnectorError,
    HealthStatus,
    ToolInvocation,
    ToolInvocationResult,
)
from avengers.core.rbac import RBACDenied, check as rbac_check
from avengers.core.tenant import TenantContext
from avengers.memory.base import MemoryStore
from avengers.schemas.config import RbacCfg
from avengers.schemas.llm import ToolSchema

_TOOLS: list[ToolSchema] = [
    ToolSchema(
        name="search",
        description=(
            "Retrieve the top-k most relevant passages from the user's "
            "ingested documents (handbooks, runbooks, past briefs, notes). "
            "Use this BEFORE falling back to web search when the user asks "
            "about anything internal."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query":   {"type": "string", "minLength": 1, "maxLength": 1000},
                "k":       {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
                "purpose": {"type": "string", "default": "rag",
                            "description": "Namespace partition — e.g. 'rag' or 'runbooks'"},
            },
            "required": ["query"],
        },
    ),
    ToolSchema(
        name="list_recent",
        description="List the most recently ingested items. Diagnostic only.",
        parameters={
            "type": "object",
            "properties": {
                "purpose": {"type": "string", "default": "rag"},
                "limit":   {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
            },
        },
    ),
]


def _namespace(ctx: TenantContext, purpose: str) -> str:
    """Same partition rule as the /memory routes — tenant/<user|shared>/<purpose>."""
    user_id = ctx.user.id if ctx.user else "shared"
    return f"{ctx.tenant_id}/{user_id}/{purpose}"


class InternalRAGConnector(ConnectorClient):
    """MCP-shaped wrapper around a MemoryStore."""

    id = "internal_rag"

    def __init__(self, memory: MemoryStore, rbac: RbacCfg | None = None) -> None:
        self._memory = memory
        # Default: any authenticated user in the tenant can query their own
        # namespace. RBAC at the connector boundary still applies if the
        # tenant tightens the config.
        self._rbac = rbac or RbacCfg()

    async def list_tools(self) -> list[ToolSchema]:
        return list(_TOOLS)

    async def invoke(self, call: ToolInvocation, ctx: TenantContext) -> ToolInvocationResult:
        groups = set(ctx.user.groups) if ctx.user else set()
        try:
            rbac_check(self._rbac, groups, resource=f"{self.id}.{call.tool}")
        except RBACDenied as exc:
            return ToolInvocationResult(tool=call.tool, ok=False, error=str(exc))

        t0 = time.monotonic()
        try:
            output = await self._dispatch(call.tool, call.args, ctx)
        except ConnectorError:
            raise
        except Exception as exc:  # noqa: BLE001
            return ToolInvocationResult(tool=call.tool, ok=False, error=str(exc))

        return ToolInvocationResult(
            tool=call.tool,
            ok=True,
            output=output,
            latency_ms=int((time.monotonic() - t0) * 1000),
        )

    async def health(self) -> HealthStatus:
        try:
            ok = await self._memory.health()
        except Exception:  # noqa: BLE001
            ok = False
        return HealthStatus(
            state="ok" if ok else "degraded",
            detail="memory store healthy" if ok else "memory store unreachable",
            checked_at=datetime.now(UTC),
        )

    async def _dispatch(self, tool: str, args: dict[str, Any], ctx: TenantContext) -> Any:
        if tool == "search":
            query = args.get("query", "")
            if not query.strip():
                raise ConnectorError(self.id, tool, "query is required")
            k = int(args.get("k", 5))
            purpose = args.get("purpose", "rag")
            ns = _namespace(ctx, purpose)
            hits = await self._memory.search(ns, query, k=k, filters=None)
            return {
                "namespace": ns,
                "query": query,
                "k": k,
                "hits": [
                    {
                        "id": h.id,
                        "text": h.text,
                        "score": h.score,
                        "source": (h.metadata or {}).get("source"),
                        "metadata": h.metadata or {},
                    }
                    for h in hits
                ],
            }

        if tool == "list_recent":
            purpose = args.get("purpose", "rag")
            limit = int(args.get("limit", 10))
            ns = _namespace(ctx, purpose)
            # Most MemoryStore impls don't have a `list` op — for the demo
            # we search for an empty-ish query and let the in-memory store
            # return its bucket. Production impls would expose a proper
            # listing method; we'd extend the Protocol then.
            hits = await self._memory.search(ns, " ", k=limit, filters=None)
            return {
                "namespace": ns,
                "items": [
                    {"id": h.id, "text": h.text[:200],
                     "source": (h.metadata or {}).get("source")}
                    for h in hits
                ],
            }

        raise ConnectorError(self.id, tool, "unknown tool")


# MCP entrypoint — connector YAML's `mcp_server` field can reference this.
server = InternalRAGConnector

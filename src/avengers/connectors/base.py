"""Connector / MCP client interface (spec §9.5).

A `ConnectorClient` wraps one MCP server (stdio or HTTP/SSE). RBAC, rate
limiting, caching, and audit are enforced *server-side* in the connector
itself (§9.5); this client exposes a uniform Python surface.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from avengers.core.tenant import TenantContext
from avengers.schemas.llm import ToolSchema


class ConnectorError(RuntimeError):
    def __init__(self, connector: str, tool: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(f"{connector}.{tool}: {message}")
        self.connector = connector
        self.tool = tool
        self.retryable = retryable


HealthState = Literal["ok", "degraded", "down"]


class HealthStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: HealthState
    detail: str = ""
    checked_at: datetime


class ToolInvocation(BaseModel):
    """What we pass to `invoke()`."""

    model_config = ConfigDict(extra="forbid")

    tool: str
    args: dict[str, Any] = Field(default_factory=dict)


class ToolInvocationResult(BaseModel):
    """What the server returns."""

    model_config = ConfigDict(extra="forbid")

    tool: str
    ok: bool
    output: Any = None
    error: str | None = None
    latency_ms: int = 0
    cached: bool = False


class ConnectorClient(Protocol):
    id: str

    async def list_tools(self) -> list[ToolSchema]: ...

    async def invoke(self, call: ToolInvocation, ctx: TenantContext) -> ToolInvocationResult: ...

    async def health(self) -> HealthStatus: ...


class ConnectorRegistry:
    """Maps connector id → client. Populated at startup from connector config."""

    def __init__(self) -> None:
        self._clients: dict[str, ConnectorClient] = {}

    def register(self, client: ConnectorClient) -> None:
        if client.id in self._clients:
            raise ValueError(f"connector already registered: {client.id}")
        self._clients[client.id] = client

    def get(self, connector_id: str) -> ConnectorClient:
        if connector_id not in self._clients:
            raise KeyError(f"unknown connector: {connector_id}")
        return self._clients[connector_id]

    def known(self) -> list[str]:
        return sorted(self._clients)

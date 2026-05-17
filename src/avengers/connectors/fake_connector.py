"""Scriptable fake connector for tests.

`enqueue(tool, handler)` registers a callable that runs when the matching tool
is invoked. Lets us drive the Director through full workflows without spinning
up real MCP servers.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from avengers.connectors.base import (
    ConnectorClient,
    ConnectorError,
    HealthStatus,
    ToolInvocation,
    ToolInvocationResult,
)
from avengers.core.tenant import TenantContext
from avengers.schemas.llm import ToolSchema

Handler = Callable[[dict[str, Any], TenantContext], Awaitable[Any]]


class FakeConnector(ConnectorClient):
    def __init__(self, connector_id: str, tools: list[ToolSchema]) -> None:
        self.id = connector_id
        self._tools = list(tools)
        self._handlers: dict[str, Handler] = {}
        self.calls: list[ToolInvocation] = []

    def enqueue(self, tool: str, handler: Handler) -> None:
        self._handlers[tool] = handler

    async def list_tools(self) -> list[ToolSchema]:
        return list(self._tools)

    async def invoke(self, call: ToolInvocation, ctx: TenantContext) -> ToolInvocationResult:
        self.calls.append(call)
        handler = self._handlers.get(call.tool)
        if handler is None:
            raise ConnectorError(self.id, call.tool, "no handler registered")
        t0 = time.monotonic()
        try:
            output = await handler(call.args, ctx)
        except ConnectorError:
            raise
        except Exception as exc:  # noqa: BLE001
            return ToolInvocationResult(
                tool=call.tool,
                ok=False,
                error=str(exc),
                latency_ms=int((time.monotonic() - t0) * 1000),
            )
        return ToolInvocationResult(
            tool=call.tool,
            ok=True,
            output=output,
            latency_ms=int((time.monotonic() - t0) * 1000),
        )

    async def health(self) -> HealthStatus:
        return HealthStatus(state="ok", checked_at=datetime.now(UTC))

"""Fynd OMS connector — skeleton.

Implements the `ConnectorClient` Protocol with stub payloads shaped like the
real Fynd Platform OMS response. Replacing this with a live MCP server that
proxies the real OMS API is one PR (drop in stdio/HTTP MCP transport, keep
the same tool names + shapes).

Tools:
  * `list_orders(status, limit)` — recent orders for the tenant
  * `fulfillment_health()`       — RTO%, NDR pile-up, courier SLA breaches
  * `returns_queue(age_days)`    — pending refund/return tickets

Server-side enforcement (see SPEC §9.5): every invocation is RBAC-checked
against the connector's `RbacCfg`, then audited by the calling agent.
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
from avengers.schemas.config import RbacCfg
from avengers.schemas.llm import ToolSchema

_TOOLS: list[ToolSchema] = [
    ToolSchema(
        name="list_orders",
        description="List recent orders, optionally filtered by status.",
        parameters={
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["placed", "shipped", "delivered", "cancelled", "rto"]},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 25},
            },
        },
    ),
    ToolSchema(
        name="fulfillment_health",
        description="Snapshot of fulfillment KPIs: RTO%, NDR pile-up, courier SLA breaches.",
        parameters={"type": "object", "properties": {}},
    ),
    ToolSchema(
        name="returns_queue",
        description="Pending refund or return tickets older than age_days.",
        parameters={
            "type": "object",
            "properties": {
                "age_days": {"type": "integer", "minimum": 0, "maximum": 90, "default": 3},
            },
        },
    ),
]


class FyndOMSConnector(ConnectorClient):
    id = "fynd_oms"

    def __init__(self, rbac: RbacCfg | None = None) -> None:
        self._rbac = rbac or RbacCfg(required_groups_any=["fynd-internal"])

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
            output = _dispatch(call.tool, call.args)
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
        return HealthStatus(state="ok", detail="stub", checked_at=datetime.now(UTC))


def _dispatch(tool: str, args: dict[str, Any]) -> Any:
    """Realistic stub payloads — replace by piping to the real Fynd OMS MCP."""
    if tool == "list_orders":
        status = args.get("status", "placed")
        limit = min(int(args.get("limit", 25)), 200)
        sample = [
            {
                "order_id": f"FYND{10_000 + i}",
                "status": status,
                "amount_inr": 1499 + i * 50,
                "courier": ["Delhivery", "Bluedart", "Ekart"][i % 3],
                "placed_at": "2026-05-17T08:00:00+05:30",
            }
            for i in range(min(5, limit))
        ]
        return {"count": len(sample), "orders": sample}

    if tool == "fulfillment_health":
        return {
            "rto_pct_7d": 4.8,
            "ndr_open": 312,
            "courier_sla_breaches_24h": [
                {"courier": "Bluedart", "lane": "North", "breach_pct": 8.2},
                {"courier": "Ekart", "lane": "South", "breach_pct": 3.1},
            ],
        }

    if tool == "returns_queue":
        age = int(args.get("age_days", 3))
        return {
            "older_than_days": age,
            "tickets": [
                {"ticket_id": "RT-9871", "order_id": "FYND10234", "reason": "size_issue", "age_days": age + 1},
                {"ticket_id": "RT-9874", "order_id": "FYND10288", "reason": "damaged", "age_days": age + 2},
            ],
        }

    raise ConnectorError("fynd_oms", tool, "unknown tool")


# MCP entrypoint — connector YAML's `mcp_server` field points here.
server = FyndOMSConnector

"""JioCommerce connector — peer of fynd_oms with the same tool surface.

Sources:
  * https://platform.jiocommerce.io
  * https://partners.jiocommerce.io/help/docs/sdk/latest/application/catalog

The tool *names* (`list_orders`, `fulfillment_health`, `returns_queue`,
`list_flagged`) match `fynd_oms` and `catalog_api` so any agent / prompt
written against Fynd works against Jio without a code change.

Pick which one runs via the env switch in `connector_registry.py`:
  COMMERCE_BACKEND=fynd    → FyndOMSConnector  (default)
  COMMERCE_BACKEND=jio     → JioCommerceConnector
  COMMERCE_BACKEND=both    → both register, tools available under
                             namespaced ids `fynd_oms.*` and `jiocommerce.*`
"""

from __future__ import annotations

import os
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

# Same tool shapes as fynd_oms — keeps agents portable.
_TOOLS: list[ToolSchema] = [
    ToolSchema(
        name="list_orders",
        description="List recent orders. JioCommerce: GET /service/application/order/v1.0/orders/.",
        parameters={
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["placed", "shipped", "delivered", "cancelled", "rto"],
                },
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
        description="Pending refund / return tickets older than age_days.",
        parameters={
            "type": "object",
            "properties": {
                "age_days": {"type": "integer", "minimum": 0, "maximum": 90, "default": 3},
            },
        },
    ),
    ToolSchema(
        name="search_catalog",
        description="JioCommerce Partners SDK: catalog.getProducts. Query by SKU or text.",
        parameters={
            "type": "object",
            "properties": {
                "q": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
            },
            "required": ["q"],
        },
    ),
    ToolSchema(
        name="list_flagged",
        description="Listings flagged for missing attributes, MAP violations, low-quality images.",
        parameters={
            "type": "object",
            "properties": {
                "severity": {"type": "string", "enum": ["low", "medium", "high"], "default": "high"},
            },
        },
    ),
]


class JioCommerceConnector(ConnectorClient):
    """Tool surface against platform.jiocommerce.io.

    The real adapter would hold an httpx.AsyncClient and call:
      GET https://api.jiocommerce.io/service/application/order/v1.0/orders/
      GET https://api.jiocommerce.io/service/application/catalog/v1.0/products/
      ...
    using `x-api-key` + `x-company-id` headers from .env. v1 returns realistic
    stub payloads so the dashboard renders; swap `_dispatch` for the live HTTP
    layer when you've confirmed your scope/auth.
    """

    id = "jiocommerce"

    def __init__(self, rbac: RbacCfg | None = None) -> None:
        self._rbac = rbac or RbacCfg(required_groups_any=["fynd-internal"])
        self._base_url = os.getenv("JIOCOMMERCE_BASE_URL", "https://api.jiocommerce.io")
        self._company_id = os.getenv("JIOCOMMERCE_COMPANY_ID", "1")

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
            output = _dispatch(call.tool, call.args, self._company_id)
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
        return HealthStatus(state="ok", detail="stub-jio", checked_at=datetime.now(UTC))


def _dispatch(tool: str, args: dict[str, Any], company_id: str) -> Any:
    base = {"source": "jiocommerce", "company_id": company_id}
    if tool == "list_orders":
        status = args.get("status", "placed")
        limit = min(int(args.get("limit", 25)), 200)
        return {
            **base,
            "count": min(5, limit),
            "orders": [
                {
                    "order_id": f"JIO{200_000 + i}",
                    "status": status,
                    "amount_inr": 999 + i * 75,
                    "courier": ["Delhivery", "XpressBees", "Bluedart"][i % 3],
                    "placed_at": "2026-05-17T08:30:00+05:30",
                }
                for i in range(min(5, limit))
            ],
        }
    if tool == "fulfillment_health":
        return {
            **base,
            "rto_pct_7d": 5.2,
            "ndr_open": 287,
            "courier_sla_breaches_24h": [
                {"courier": "XpressBees", "lane": "East", "breach_pct": 6.8},
            ],
        }
    if tool == "returns_queue":
        age = int(args.get("age_days", 3))
        return {
            **base,
            "older_than_days": age,
            "tickets": [
                {"ticket_id": "JIO-RT-441", "order_id": "JIO200122", "reason": "wrong_size", "age_days": age + 2},
            ],
        }
    if tool == "search_catalog":
        q = args.get("q", "")
        return {
            **base,
            "query": q,
            "items": [
                {"sku": "JIO-TS-RED-M", "name": f"{q} tee (red, M)", "stock": 12, "mrp_inr": 999},
                {"sku": "JIO-TS-BLU-L", "name": f"{q} tee (blue, L)", "stock": 3, "mrp_inr": 999},
            ],
        }
    if tool == "list_flagged":
        sev = args.get("severity", "high")
        return {
            **base,
            "severity": sev,
            "items": [
                {"sku": "JIO-DR-BLK-S", "issue": "missing_dimensions", "severity": sev},
            ],
        }
    raise ConnectorError("jiocommerce", tool, "unknown tool")


server = JioCommerceConnector

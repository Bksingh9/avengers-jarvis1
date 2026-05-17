"""Catalog API connector — skeleton.

Single-tool connector the CatalogAgent uses to surface listing-quality issues
(missing attributes, MAP violations, low-quality images). Real implementation
will proxy Fynd Platform's catalog APIs over MCP.
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
        name="list_flagged",
        description="Listings flagged for missing attributes, MAP violations, or low-quality images.",
        parameters={
            "type": "object",
            "properties": {
                "category": {"type": "string"},
                "severity": {"type": "string", "enum": ["low", "medium", "high"], "default": "high"},
            },
        },
    ),
]


class CatalogAPIConnector(ConnectorClient):
    id = "catalog_api"

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
    if tool == "list_flagged":
        sev = args.get("severity", "high")
        return {
            "severity": sev,
            "items": [
                {"sku": "TS-RED-M", "issue": "missing_dimensions", "severity": sev},
                {"sku": "NK-BLU-L", "issue": "map_violation", "current_price": 1199, "map_price": 1499},
                {"sku": "DR-BLK-S", "issue": "low_image_quality", "score": 0.41},
            ],
        }
    raise ConnectorError("catalog_api", tool, "unknown tool")


server = CatalogAPIConnector

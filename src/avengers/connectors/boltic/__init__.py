"""Boltic connector — skeleton.

Boltic is Fynd's data-integration platform. The Inventory specialist uses it
to spot upstream data freshness issues that would otherwise turn into stale
stockout signals.
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
        name="list_pipelines",
        description="Names + last-run status of every data pipeline in the workspace.",
        parameters={"type": "object", "properties": {}},
    ),
    ToolSchema(
        name="recent_runs",
        description="Execution history for one pipeline.",
        parameters={
            "type": "object",
            "properties": {
                "pipeline_id": {"type": "string"},
                "hours": {"type": "integer", "minimum": 1, "maximum": 168, "default": 24},
            },
            "required": ["pipeline_id"],
        },
    ),
    ToolSchema(
        name="failed_jobs",
        description="Failed jobs across all pipelines in the rolling window.",
        parameters={
            "type": "object",
            "properties": {
                "window_hours": {"type": "integer", "minimum": 1, "maximum": 72, "default": 24},
            },
        },
    ),
]


class BolticConnector(ConnectorClient):
    id = "boltic"

    def __init__(self, rbac: RbacCfg | None = None) -> None:
        # Boltic is internal-tools, so default to the same gating as OMS.
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
    if tool == "list_pipelines":
        return {
            "pipelines": [
                {"id": "pl_inv_sync", "name": "Inventory Sync (Vinculum→DW)", "last_status": "ok"},
                {"id": "pl_catalog",  "name": "Catalog Snapshot",              "last_status": "ok"},
                {"id": "pl_returns",  "name": "Returns Reconciliation",        "last_status": "fail"},
            ]
        }
    if tool == "recent_runs":
        pid = args.get("pipeline_id", "unknown")
        hours = int(args.get("hours", 24))
        return {
            "pipeline_id": pid,
            "window_hours": hours,
            "runs": [
                {"run_id": f"r{i}", "status": "ok" if i % 4 else "fail", "duration_s": 12 + i}
                for i in range(6)
            ],
        }
    if tool == "failed_jobs":
        return {
            "window_hours": int(args.get("window_hours", 24)),
            "failures": [
                {"pipeline_id": "pl_returns", "run_id": "r122", "error": "schema_drift in column 'sku'"},
            ],
        }
    raise ConnectorError("boltic", tool, "unknown tool")


server = BolticConnector

"""Connector plane (spec §9.5).

Every data source is an MCP server exposed through `ConnectorClient`. The
Director and specialists discover tools via the MCP protocol — they do not
import connector implementations.
"""

from avengers.connectors.base import (
    ConnectorClient,
    ConnectorError,
    ConnectorRegistry,
    HealthStatus,
    ToolInvocation,
    ToolInvocationResult,
)

__all__ = [
    "ConnectorClient",
    "ConnectorError",
    "ConnectorRegistry",
    "HealthStatus",
    "ToolInvocation",
    "ToolInvocationResult",
]

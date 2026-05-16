"""Load + validate + cache YAML config from `config/` (spec §7).

Hot reload on SIGHUP: call `reload()` from the signal handler.
"""

from __future__ import annotations

import logging
import re
import threading
from pathlib import Path
from typing import Any

import yaml

from avengers.schemas.config import (
    AgentConfig,
    ConnectorConfig,
    PolicyConfig,
    TenantConfig,
)

logger = logging.getLogger(__name__)

_VAR_RE = re.compile(r"\$\{([^}]+)\}|\$([a-zA-Z_][a-zA-Z0-9_.]*)")


class ConfigStore:
    """Thread-safe in-memory registry of validated configs."""

    def __init__(self, config_dir: Path) -> None:
        self._config_dir = config_dir
        self._lock = threading.RLock()
        self._tenants: dict[str, TenantConfig] = {}
        self._agents: dict[str, AgentConfig] = {}
        self._connectors: dict[str, ConnectorConfig] = {}
        self._policies: dict[str, PolicyConfig] = {}

    # ---- public API -------------------------------------------------------

    def reload(self) -> None:
        with self._lock:
            self._tenants = self._load_dir("tenants", TenantConfig)
            self._agents = self._load_dir("agents", AgentConfig)
            self._connectors = self._load_dir("connectors", ConnectorConfig)
            self._policies = self._load_dir("policies", PolicyConfig)
            logger.info(
                "config_loaded tenants=%d agents=%d connectors=%d policies=%d",
                len(self._tenants),
                len(self._agents),
                len(self._connectors),
                len(self._policies),
            )

    def tenant(self, tenant_id: str) -> TenantConfig:
        with self._lock:
            return self._tenants[tenant_id]

    def agent(self, agent_id: str) -> AgentConfig:
        with self._lock:
            return self._agents[agent_id]

    def connector(self, connector_id: str) -> ConnectorConfig:
        with self._lock:
            return self._connectors[connector_id]

    def policies(self) -> list[PolicyConfig]:
        with self._lock:
            return list(self._policies.values())

    def all_tenants(self) -> list[TenantConfig]:
        with self._lock:
            return list(self._tenants.values())

    def all_agents(self) -> list[AgentConfig]:
        with self._lock:
            return list(self._agents.values())

    # ---- internals --------------------------------------------------------

    def _load_dir(self, subdir: str, model: type) -> dict[str, Any]:
        out: dict[str, Any] = {}
        d = self._config_dir / subdir
        if not d.exists():
            return out
        for p in sorted(d.glob("*.yaml")):
            try:
                raw = yaml.safe_load(p.read_text()) or {}
                obj = model.model_validate(raw)
                out[obj.id] = obj
            except Exception as exc:  # noqa: BLE001
                logger.error("config_invalid file=%s error=%s", p, exc)
                raise
        return out


def interpolate(value: Any, ctx: dict[str, Any]) -> Any:
    """Expand `${tenant.timezone}` / `$tenant.timezone` placeholders.

    Used at agent-config bind time to inline tenant-scoped routing. Strings only;
    nested dicts/lists are walked recursively.
    """

    if isinstance(value, str):
        def _sub(m: re.Match[str]) -> str:
            key = m.group(1) or m.group(2)
            cur: Any = ctx
            for part in key.split("."):
                if isinstance(cur, dict):
                    cur = cur.get(part)
                else:
                    cur = getattr(cur, part, None)
                if cur is None:
                    return m.group(0)  # leave unresolved
            return str(cur)

        return _VAR_RE.sub(_sub, value)
    if isinstance(value, list):
        return [interpolate(v, ctx) for v in value]
    if isinstance(value, dict):
        return {k: interpolate(v, ctx) for k, v in value.items()}
    return value

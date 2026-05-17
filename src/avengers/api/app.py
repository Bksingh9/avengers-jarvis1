"""App factory + dependency container.

We don't use a heavy DI library; one `AppContainer` carries the wiring and is
stashed on `app.state.container` for the route modules to pull from.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from avengers.agents.director import Director
from avengers.connectors.base import ConnectorRegistry
from avengers.core.audit import Auditor
from avengers.core.budget import BudgetTracker
from avengers.core.config_loader import ConfigStore
from avengers.core.policy import PolicyEngine
from avengers.delivery.base import DeliveryChannel
from avengers.identity.base import IdentityProvider
from avengers.llm.router import LLMRouter
from avengers.memory.fs_memory import FilesystemMemory
from avengers.workflows.approval import ApprovalQueue


@dataclass(slots=True)
class AppContainer:
    """Everything an API route might need. Built by `bootstrap()` at startup."""

    config_store: ConfigStore
    identity: IdentityProvider
    router: LLMRouter
    connectors: ConnectorRegistry
    policies: PolicyEngine
    auditor: Auditor
    approvals: ApprovalQueue
    director: Director
    delivery_channels: dict[str, DeliveryChannel] = field(default_factory=dict)
    budget: BudgetTracker | None = None
    memory: FilesystemMemory | None = None
    last_briefs: dict[str, Any] = field(default_factory=dict)
    # ^ in-memory map (tenant_id, user_id, for_date) -> MorningBrief; production
    #   reads from Postgres instead.


def create_app(container: AppContainer) -> FastAPI:
    from avengers.api.routes import (
        admin,
        agents,
        approvals,
        briefs,
        scim,
        stream,
        tenants,
        users,
    )

    app = FastAPI(title="AVENGERS Control Plane", version="0.1.0")
    app.state.container = container

    # CORS — env-driven so the deployed dashboard origin (Vercel, etc.) can be
    # added without a code change. `AVENGERS_CORS_ORIGINS` is comma-separated;
    # defaults cover local dev (Vite/Next) and the docker-compose web service.
    default_origins = "http://localhost:3000,http://web:3000"
    origins_csv = os.getenv("AVENGERS_CORS_ORIGINS", default_origins)
    allow_origins = [o.strip() for o in origins_csv.split(",") if o.strip()]
    # If any origin is a regex pattern (contains '*' or 'https://*.vercel.app'),
    # use `allow_origin_regex` so Vercel preview URLs work too.
    regex_origins = [o for o in allow_origins if "*" in o]
    plain_origins = [o for o in allow_origins if "*" not in o]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=plain_origins,
        allow_origin_regex=("|".join(_to_regex(o) for o in regex_origins)) or None,
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
    )

    @app.get("/healthz")
    async def healthz() -> dict:
        return {
            "status": "ok",
            "tenants": len(container.config_store.all_tenants()),
            "agents": len(container.config_store.all_agents()),
            "connectors_known": container.connectors.known(),
        }

    app.include_router(tenants.router)
    app.include_router(users.router)
    app.include_router(agents.router)
    app.include_router(briefs.router)
    app.include_router(stream.router)
    app.include_router(approvals.router)
    app.include_router(scim.router)
    app.include_router(admin.router)
    return app


def _to_regex(pattern: str) -> str:
    """Turn `https://*.vercel.app` into the equivalent anchored regex.

    Only `*` is treated as a wildcard. Everything else is escaped so a stray
    `.` in the env value can't accidentally match an extra character.
    """
    import re

    parts = pattern.split("*")
    return "^" + ".*".join(re.escape(p) for p in parts) + "$"

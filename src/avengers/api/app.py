"""App factory + dependency container.

We don't use a heavy DI library; one `AppContainer` carries the wiring and is
stashed on `app.state.container` for the route modules to pull from.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI

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
        tenants,
        users,
    )

    app = FastAPI(title="AVENGERS Control Plane", version="0.1.0")
    app.state.container = container

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
    app.include_router(approvals.router)
    app.include_router(scim.router)
    app.include_router(admin.router)
    return app

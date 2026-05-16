"""Tenant context — propagated through every request and tool call.

Every adapter (LLM, memory, connector, delivery) takes a `TenantContext` and
enforces scoping based on it. No global mutable tenant state.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass

from avengers.schemas.config import TenantConfig
from avengers.schemas.identity import User


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Immutable per-request context."""

    tenant: TenantConfig
    user: User | None = None
    correlation_id: str | None = None

    @property
    def tenant_id(self) -> str:
        return self.tenant.id

    @property
    def user_id(self) -> str | None:
        return self.user.id if self.user is not None else None

    def with_user(self, user: User) -> "TenantContext":
        return TenantContext(tenant=self.tenant, user=user, correlation_id=self.correlation_id)


_current: ContextVar[TenantContext | None] = ContextVar("avengers_tenant_ctx", default=None)


def current_context() -> TenantContext:
    ctx = _current.get()
    if ctx is None:
        raise RuntimeError("TenantContext not set; call set_current() at the request boundary")
    return ctx


def set_current(ctx: TenantContext) -> ContextVar:
    """Set the context for the current async task. Returns the token to reset()."""
    return _current.set(ctx)  # type: ignore[return-value]


def reset_current(token) -> None:  # type: ignore[no-untyped-def]
    _current.reset(token)

"""FastAPI dependencies: auth + tenant resolution + container access.

All routes that touch tenant data MUST depend on `require_tenant_ctx`. It:
  1. extracts `Authorization: Bearer <token>`,
  2. calls `IdentityProvider.verify_token(token)` to get the `User`,
  3. looks up the user's tenant config in `ConfigStore`,
  4. builds a `TenantContext`.

Cross-tenant access is rejected here, not deeper in the call stack.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Path, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from avengers.api.app import AppContainer
from avengers.core.tenant import TenantContext
from avengers.schemas.identity import User

_bearer = HTTPBearer(auto_error=True)


def get_container(request: Request) -> AppContainer:
    return request.app.state.container  # type: ignore[no-any-return]


async def require_user(
    creds: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> User:
    try:
        return await container.identity.verify_token(creds.credentials)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


async def require_tenant_ctx(
    tenant_id: Annotated[str, Path(pattern=r"^[a-z0-9_-]+$")],
    user: Annotated[User, Depends(require_user)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> TenantContext:
    if user.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="cross-tenant access denied"
        )
    try:
        tenant = container.config_store.tenant(tenant_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown tenant") from exc
    return TenantContext(tenant=tenant, user=user)


async def require_admin_ctx(
    ctx: Annotated[TenantContext, Depends(require_tenant_ctx)],
) -> TenantContext:
    if ctx.user is None or "avengers-admin" not in ctx.user.groups:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="admin role required"
        )
    return ctx

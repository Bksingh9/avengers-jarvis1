"""Control-plane FastAPI app (spec §6 src/avengers/api).

Auth flow:
  Authorization: Bearer <token> → IdentityProvider.verify_token →
  TenantContext is bound for the request via dependency injection.

Tenant scope is enforced at the dependency layer: every route that operates
on tenant data takes `ctx: TenantContext = Depends(require_tenant_ctx)`.
"""

from avengers.api.app import AppContainer, create_app

__all__ = ["AppContainer", "create_app"]

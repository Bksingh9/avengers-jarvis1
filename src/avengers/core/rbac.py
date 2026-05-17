"""RBAC enforced at the connector boundary (spec §12.2).

The connector reads its own `RbacCfg` and asks `check()` whether the current
user may invoke it. Group membership comes from the `IdentityProvider`.
"""

from __future__ import annotations

from avengers.schemas.config import RbacCfg


class RBACDenied(PermissionError):
    def __init__(self, resource: str, reason: str) -> None:
        super().__init__(f"rbac denied {resource}: {reason}")
        self.resource = resource
        self.reason = reason


def check(rbac: RbacCfg, user_groups: set[str], *, resource: str) -> None:
    """Raise `RBACDenied` if the user doesn't satisfy the rule."""
    if rbac.required_groups_any:
        if not (set(rbac.required_groups_any) & user_groups):
            raise RBACDenied(resource, f"needs any of {sorted(rbac.required_groups_any)}")
    if rbac.required_groups_all:
        missing = set(rbac.required_groups_all) - user_groups
        if missing:
            raise RBACDenied(resource, f"missing {sorted(missing)}")

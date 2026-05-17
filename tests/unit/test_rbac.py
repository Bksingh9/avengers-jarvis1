import pytest

from avengers.core.rbac import RBACDenied, check
from avengers.schemas.config import RbacCfg


def test_any_group_satisfied():
    rbac = RbacCfg(required_groups_any=["data-readers"])
    check(rbac, {"data-readers", "x"}, resource="snowflake")


def test_any_group_unsatisfied():
    rbac = RbacCfg(required_groups_any=["data-readers"])
    with pytest.raises(RBACDenied):
        check(rbac, {"other"}, resource="snowflake")


def test_all_groups_required():
    rbac = RbacCfg(required_groups_all=["a", "b"])
    check(rbac, {"a", "b", "c"}, resource="x")
    with pytest.raises(RBACDenied):
        check(rbac, {"a"}, resource="x")


def test_empty_rbac_is_permissive():
    check(RbacCfg(), set(), resource="x")

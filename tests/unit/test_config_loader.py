from pathlib import Path

import pytest

from avengers.core.config_loader import ConfigStore, interpolate


def _write_tenant(d: Path) -> None:
    (d / "tenants").mkdir(parents=True)
    (d / "tenants" / "acme.yaml").write_text(
        """
id: acme
name: ACME Corp
region: ap-south-1
locale: en-IN
timezone: Asia/Kolkata
identity:
  provider: oidc
  issuer: https://acme.okta.com
secrets_namespace: avengers/acme
kms_key_arn: arn:aws:kms:ap-south-1:000:key/abc
audit:
  bucket: avengers-audit-acme
budgets:
  daily_usd_cap: 250
  per_user_usd_cap: 1.5
llm_routing:
  default: bedrock:claude-sonnet-4-6
agents_enabled: [meetings, markets]
"""
    )


def test_loads_and_validates(tmp_path: Path):
    _write_tenant(tmp_path)
    store = ConfigStore(tmp_path)
    store.reload()
    t = store.tenant("acme")
    assert t.id == "acme"
    assert t.budgets.daily_usd_cap == 250
    assert "meetings" in t.agents_enabled


def test_invalid_yaml_raises(tmp_path: Path):
    (tmp_path / "tenants").mkdir()
    (tmp_path / "tenants" / "broken.yaml").write_text("id: x\n")  # missing required fields
    store = ConfigStore(tmp_path)
    with pytest.raises(Exception):
        store.reload()


def test_interpolate_dotted_path():
    ctx = {"tenant": {"id": "acme", "region": "ap-south-1"}}
    assert interpolate("${tenant.id}-${tenant.region}", ctx) == "acme-ap-south-1"
    assert interpolate("plain", ctx) == "plain"
    assert interpolate("$tenant.id", ctx) == "acme"
    # unresolved placeholders survive as-is
    assert interpolate("${tenant.missing}", ctx) == "${tenant.missing}"


def test_interpolate_walks_dict_and_list():
    ctx = {"tenant": {"timezone": "Asia/Kolkata"}}
    out = interpolate(
        {"schedule": {"tz": "${tenant.timezone}"}, "list": ["${tenant.timezone}", "literal"]},
        ctx,
    )
    assert out["schedule"]["tz"] == "Asia/Kolkata"
    assert out["list"] == ["Asia/Kolkata", "literal"]

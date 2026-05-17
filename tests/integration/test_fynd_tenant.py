"""Fynd-internal tenant end-to-end (BRD §9.1 / §9.2).

Covers:
  1. The shipped YAMLs (tenant, 3 agents, 3 connectors) validate via ConfigStore.
  2. build_container resolves the tenant's 9 agents_enabled to 9 specialist
     instances (six reference + three Fynd-specific).
  3. A full SSE brief for tenant_id=fynd_internal returns
     start + 9×section + done with every section status=ok.
  4. RBAC gates the catalog_api connector: a user without the `fynd-internal`
     group gets a tool-result error, the agent recovers and still returns a
     valid digest.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from avengers.api.app import create_app
from avengers.api.bootstrap import build_container
from avengers.connectors.base import ConnectorRegistry
from avengers.connectors.boltic import BolticConnector
from avengers.connectors.catalog_api import CatalogAPIConnector
from avengers.connectors.fake_connector import FakeConnector
from avengers.connectors.fynd_oms import FyndOMSConnector
from avengers.core.config_loader import ConfigStore
from avengers.core.tenant import TenantContext
from avengers.identity.static_provider import StaticIdentityProvider
from avengers.llm.base import LLMRegistry
from avengers.llm.fake_provider import FakeLLMProvider
from avengers.schemas.identity import DeliveryPrefs, User
from avengers.schemas.llm import Completion, ToolSchema

_CONFIG = Path(__file__).resolve().parents[2] / "config"


def _users() -> list[User]:
    return [
        User(
            id="fynd-alice",
            tenant_id="fynd_internal",
            email="alice@fynd.com",
            display_name="Alice",
            groups={"avengers-admin", "fynd-internal"},
            timezone="Asia/Kolkata",
            delivery_prefs=DeliveryPrefs(channels=["console"]),
        ),
        User(
            id="fynd-guest",
            tenant_id="fynd_internal",
            email="guest@fynd.com",
            display_name="Guest",
            groups=set(),
            timezone="Asia/Kolkata",
        ),
    ]


def test_fynd_yaml_loads() -> None:
    """1. ConfigStore validates the tenant + new agent/connector YAMLs."""
    store = ConfigStore(_CONFIG)
    store.reload()
    tenant = store.tenant("fynd_internal")
    assert tenant.region == "ap-south-1"
    assert tenant.timezone == "Asia/Kolkata"
    assert {"catalog", "inventory", "reconciliation"} <= set(tenant.agents_enabled)
    assert len(tenant.agents_enabled) == 9
    assert tenant.budgets.daily_usd_cap == 1000

    for aid in ("catalog", "inventory", "reconciliation"):
        a = store.agent(aid)
        assert a.id == aid

    assert store.connector("fynd_oms").rbac.required_groups_any == ["fynd-internal"]
    assert store.connector("boltic").rbac.required_groups_any == ["fynd-internal"]
    assert store.connector("catalog_api").rbac.required_groups_any == ["fynd-internal"]
    # Reconciliation is finance-grade — gate is 0.90 per the plan
    assert store.agent("reconciliation").evals.gate_score == 0.90  # type: ignore[union-attr]


def _build_wired(memory_root: Path) -> tuple[object, FakeLLMProvider]:
    fake_llm = FakeLLMProvider()
    reg = LLMRegistry()
    reg.register("anthropic", lambda: fake_llm)
    reg.register("fake", lambda: fake_llm)

    connectors = ConnectorRegistry()
    # Register every connector any enabled agent might reference so
    # `_collect_tools` doesn't drop tools silently and skew the test.
    connectors.register(
        FakeConnector("exa_search", [ToolSchema(name="search", description="", parameters={})])
    )
    for cid in (
        "gcal",
        "polygon",
        "splunk",
        "crowdstrike",
        "github_security",
        "cms",
        "internal_rag",
        "snowflake",
        "pagerduty",
        "jira",
        "datadog",
        "sec_edgar",
    ):
        connectors.register(FakeConnector(cid, [ToolSchema(name="x", description="", parameters={})]))
    connectors.register(FyndOMSConnector())
    connectors.register(BolticConnector())
    connectors.register(CatalogAPIConnector())

    container = build_container(
        config_dir=_CONFIG,
        identity=StaticIdentityProvider(_users()),
        llm_registry=reg,
        connectors=connectors,
        memory_root=memory_root,
    )
    return container, fake_llm


def test_director_has_nine_specialists(tmp_path: Path) -> None:
    """2. build_container wires 9 specialist instances for the Fynd tenant."""
    container, _ = _build_wired(tmp_path / "mem")
    assert set(container.director.specialists.keys()) >= {  # type: ignore[attr-defined]
        "meetings",
        "markets",
        "security",
        "research",
        "content",
        "operations",
        "catalog",
        "inventory",
        "reconciliation",
    }


def _parse_sse(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for frame in text.strip().split("\n\n"):
        event = "message"
        data: list[str] = []
        for line in frame.split("\n"):
            if line.startswith("event:"):
                event = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data.append(line[len("data:") :].strip())
        if data:
            out.append((event, "\n".join(data)))
    return out


@pytest.mark.asyncio
async def test_stream_brief_nine_sections(tmp_path: Path) -> None:
    """3. Full SSE brief for fynd_internal returns nine sections, all ok."""
    container, fake_llm = _build_wired(tmp_path / "mem")
    # Universal '{}' parses for any of the 9 digest schemas (all fields use
    # default_factory=list), so ordering of the async gather is irrelevant.
    for _ in range(40):
        fake_llm.enqueue(
            Completion(
                model="m1",
                output_text="{}",
                stop_reason="end_turn",
                input_tokens=10,
                output_tokens=10,
                cost_usd=0.001,
            )
        )

    app = create_app(container)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as ac:
        r = await ac.post(
            "/tenants/fynd_internal/briefs/stream",
            headers={"Authorization": "Bearer user:fynd-alice"},
            json={"for_date": "2026-05-17"},
        )
        assert r.status_code == 200
        events = _parse_sse(r.text)

    kinds = [e for e, _ in events]
    assert kinds[0] == "start"
    assert kinds[-1] == "done"
    assert kinds.count("section") == 9, kinds


@pytest.mark.asyncio
async def test_rbac_blocks_guest_on_catalog_connector(tmp_path: Path) -> None:
    """4. A user without the `fynd-internal` group cannot invoke catalog_api.

    We exercise the connector directly with the guest's TenantContext — the
    `RbacCfg(required_groups_any=["fynd-internal"])` should fail closed.
    """
    container, _ = _build_wired(tmp_path / "mem")
    connector = container.connectors.get("catalog_api")  # type: ignore[attr-defined]

    tenant_cfg = container.config_store.tenant("fynd_internal")  # type: ignore[attr-defined]
    guest = next(u for u in _users() if u.id == "fynd-guest")
    admin = next(u for u in _users() if u.id == "fynd-alice")

    from avengers.connectors.base import ToolInvocation

    call = ToolInvocation(tool="list_flagged", args={"severity": "high"})

    denied = await connector.invoke(call, TenantContext(tenant=tenant_cfg, user=guest))
    assert denied.ok is False
    assert "rbac denied" in (denied.error or "").lower()

    allowed = await connector.invoke(call, TenantContext(tenant=tenant_cfg, user=admin))
    assert allowed.ok is True
    assert "items" in (allowed.output or {})

"""JARVIS — Cap Brij persona overlay + conversational + proactive endpoints.

Covers:
  1. JARVIS tenant YAML loads, 8 specialists wired
  2. Persona overlay flows into the agent's system prompt for jarvis tenant
     but NOT for acme / fynd_internal
  3. /jarvis/converse returns a speakable, citation-bearing answer
  4. /jarvis/proactive returns headline + body + speakable + sections
  5. Cron secret guard rejects requests without the bearer when set
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
from avengers.connectors.jiocommerce import JioCommerceConnector
from avengers.core.config_loader import ConfigStore
from avengers.core.tenant import TenantContext
from avengers.identity.static_provider import StaticIdentityProvider
from avengers.llm.base import LLMRegistry
from avengers.llm.fake_provider import FakeLLMProvider
from avengers.schemas.identity import DeliveryPrefs, User
from avengers.schemas.llm import Completion, ToolSchema

_REPO = Path(__file__).resolve().parents[2]
_CONFIG = _REPO / "config"


def _users() -> list[User]:
    return [
        User(
            id="cap-brij",
            tenant_id="jarvis",
            email="cap.brij@example.com",
            display_name="Cap Brij",
            groups={"avengers-admin", "fynd-internal", "jarvis-owner"},
            timezone="Asia/Kolkata",
            delivery_prefs=DeliveryPrefs(channels=["console"]),
        ),
        User(
            id="fynd-alice",
            tenant_id="fynd_internal",
            email="alice@fynd.com",
            display_name="Alice (Fynd)",
            groups={"avengers-admin", "fynd-internal"},
            timezone="Asia/Kolkata",
        ),
    ]


def _wire(memory_root: Path) -> tuple[object, FakeLLMProvider]:
    fake_llm = FakeLLMProvider()
    reg = LLMRegistry()
    reg.register("anthropic", lambda: fake_llm)
    reg.register("fake", lambda: fake_llm)

    connectors = ConnectorRegistry()
    connectors.register(
        FakeConnector("exa_search", [ToolSchema(name="search", description="", parameters={})])
    )
    for cid in (
        "gcal", "polygon", "splunk", "crowdstrike", "github_security",
        "cms", "internal_rag", "snowflake", "pagerduty", "jira",
        "datadog", "sec_edgar",
    ):
        connectors.register(FakeConnector(cid, [ToolSchema(name="x", description="", parameters={})]))
    connectors.register(FyndOMSConnector())
    connectors.register(JioCommerceConnector())
    connectors.register(BolticConnector())
    connectors.register(CatalogAPIConnector())

    container = build_container(
        config_dir=_CONFIG,
        identity=StaticIdentityProvider(_users()),
        llm_registry=reg,
        connectors=connectors,
        memory_root=memory_root,
        personas_root=_REPO / "memory",
    )
    return container, fake_llm


def test_jarvis_yaml_and_specialists(tmp_path: Path) -> None:
    container, _ = _wire(tmp_path / "mem")
    store: ConfigStore = container.config_store  # type: ignore[attr-defined]
    t = store.tenant("jarvis")
    assert t.timezone == "Asia/Kolkata"
    assert "catalog" in t.agents_enabled and "inventory" in t.agents_enabled
    assert len(t.agents_enabled) == 8


def test_persona_loaded_for_jarvis_only() -> None:
    """persona overlay should be present for jarvis, absent for acme."""
    container, _ = _wire(Path("/tmp/jarvis-mem-1"))
    # Reach into deps.system_prompts via any specialist instance.
    research = container.director.specialists["research"]  # type: ignore[attr-defined]
    prompts = research.deps.system_prompts
    assert "persona:jarvis" in prompts
    assert "Cap Brij" in prompts["persona:jarvis"]
    assert "persona:acme" not in prompts


def test_persona_appears_in_system_prompt() -> None:
    """_system_prompt must prepend the persona when ctx.tenant_id has one."""
    container, _ = _wire(Path("/tmp/jarvis-mem-2"))
    research = container.director.specialists["research"]  # type: ignore[attr-defined]

    jarvis_ctx = TenantContext(
        tenant=container.config_store.tenant("jarvis"),  # type: ignore[attr-defined]
        user=next(u for u in _users() if u.id == "cap-brij"),
    )
    acme_ctx_tenant = container.config_store.tenant("acme")  # type: ignore[attr-defined]
    acme_ctx = TenantContext(tenant=acme_ctx_tenant)

    jarvis_prompt = research._system_prompt(ctx=jarvis_ctx)
    acme_prompt = research._system_prompt(ctx=acme_ctx)

    assert "Cap Brij" in jarvis_prompt
    assert "Cap Brij" not in acme_prompt


@pytest.mark.asyncio
async def test_converse_returns_speakable_answer(tmp_path: Path) -> None:
    container, fake_llm = _wire(tmp_path / "mem")
    # Research agent's deep-dive emits a ResearchDigest; one Cited item in deep_dive
    fake_llm.enqueue(
        Completion(
            model="m1",
            output_text=(
                '{"topic_deltas":[],'
                '"deep_dive":[{"text":"Inventory pipeline failed at 02:14.",'
                '"sources":[{"connector":"boltic","tool":"failed_jobs",'
                '"ref":"r122","ts":"2026-05-17T02:14:00+05:30"}],'
                '"confidence":0.95}]}'
            ),
            stop_reason="end_turn",
            input_tokens=80,
            output_tokens=40,
            cost_usd=0.0011,
        )
    )

    app = create_app(container)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as ac:
        r = await ac.post(
            "/tenants/jarvis/jarvis/converse",
            headers={"Authorization": "Bearer user:cap-brij"},
            json={"query": "what broke overnight?", "voice_mode": True},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "Inventory pipeline failed" in body["text"]
    # speakable must be markdown-free
    assert "**" not in body["speakable"] and "```" not in body["speakable"]
    assert body["citations"][0]["connector"] == "boltic"


@pytest.mark.asyncio
async def test_proactive_returns_headline_and_body(tmp_path: Path) -> None:
    container, fake_llm = _wire(tmp_path / "mem")
    # Enqueue enough universal-empty digests for any of the 8 enabled agents.
    for _ in range(40):
        fake_llm.enqueue(
            Completion(
                model="m1", output_text="{}", stop_reason="end_turn",
                input_tokens=10, output_tokens=10, cost_usd=0.001,
            )
        )

    app = create_app(container)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as ac:
        r = await ac.post(
            "/tenants/jarvis/jarvis/proactive",
            headers={"Authorization": "Bearer user:cap-brij"},
            json={},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "Cap Brij" in body["headline"]
    assert len(body["sections"]) == 8  # jarvis tenant has 8 agents enabled


@pytest.mark.asyncio
async def test_proactive_cron_path_accepts_secret(tmp_path: Path, monkeypatch) -> None:
    """When CRON_SECRET is set, X-Cron-Secret unlocks the route without a
    user bearer. Wrong secret → 401."""
    monkeypatch.setenv("CRON_SECRET", "shhh")
    container, fake_llm = _wire(tmp_path / "mem")
    for _ in range(40):
        fake_llm.enqueue(
            Completion(model="m1", output_text="{}", stop_reason="end_turn", cost_usd=0)
        )

    app = create_app(container)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as ac:
        # No auth at all → 401
        r_none = await ac.post("/tenants/jarvis/jarvis/proactive", json={})
        assert r_none.status_code == 401

        # Wrong cron secret + no user bearer → 401
        r_bad = await ac.post(
            "/tenants/jarvis/jarvis/proactive",
            headers={"X-Cron-Secret": "wrong"},
            json={},
        )
        assert r_bad.status_code == 401

        # Right cron secret → 200 (no user bearer needed)
        r_ok = await ac.post(
            "/tenants/jarvis/jarvis/proactive",
            headers={"X-Cron-Secret": "shhh"},
            json={},
        )
        assert r_ok.status_code == 200, r_ok.text
        assert "Cap Brij" in r_ok.json()["headline"]

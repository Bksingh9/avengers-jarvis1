"""Full morning-brief workflow: 3 specialists in parallel + delivery + audit."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from avengers.agents.base import AgentDeps
from avengers.agents.director import Director
from avengers.agents.markets import MarketsAgent
from avengers.agents.meetings import MeetingsAgent
from avengers.agents.research import ResearchAgent
from avengers.connectors.base import ConnectorRegistry
from avengers.connectors.fake_connector import FakeConnector
from avengers.core.audit import Auditor, InMemoryAuditSink
from avengers.core.policy import PolicyEngine
from avengers.core.tenant import TenantContext
from avengers.delivery.console_channel import ConsoleChannel
from avengers.llm.base import LLMRegistry
from avengers.llm.fake_provider import FakeLLMProvider
from avengers.llm.router import LLMRouter
from avengers.memory.fs_memory import FilesystemMemory
from avengers.schemas.config import (
    AgentConfig,
    AuditCfg,
    BudgetCfg,
    IdentityCfg,
    LimitsCfg,
    LLMRoutingCfg,
    ModelCfg,
    TenantConfig,
    ToolsCfg,
)
from avengers.schemas.identity import DeliveryPrefs, User
from avengers.schemas.llm import Completion, ToolSchema
from avengers.workflows.morning_brief import run_morning_brief


def _ctx() -> TenantContext:
    return TenantContext(
        tenant=TenantConfig(
            id="acme",
            name="ACME",
            region="us",
            identity=IdentityCfg(provider="oidc", issuer="https://x"),
            secrets_namespace="ns",
            kms_key_arn="arn",
            audit=AuditCfg(bucket="b"),
            budgets=BudgetCfg(daily_usd_cap=100, per_user_usd_cap=10),
            llm_routing=LLMRoutingCfg(default="fake:m1"),
        )
    )


def _agent_cfg(agent_id: str, connector_id: str) -> AgentConfig:
    return AgentConfig(
        id=agent_id,
        display_name=agent_id.title(),
        version="0.1.0",
        model=ModelCfg(primary="fake:m1"),
        prompt=f"prompts/{agent_id}.md",
        input_schema=f"{agent_id.title()}Input",
        output_schema=f"{agent_id.title()}Digest",
        tools=ToolsCfg(mcp=[connector_id]),
        limits=LimitsCfg(max_turns=2, wallclock_seconds=5),
    )


def _ok_completion(digest_json: str) -> Completion:
    return Completion(
        model="m1",
        output_text=digest_json,
        stop_reason="end_turn",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.001,
    )


@pytest.mark.asyncio
async def test_morning_brief_three_specialists(tmp_path: Path):
    fake_llm = FakeLLMProvider()
    reg = LLMRegistry()
    reg.register("fake", lambda: fake_llm)
    router = LLMRouter(registry=reg)

    connectors = ConnectorRegistry()
    for cid in ("gcal", "polygon", "exa_search"):
        c = FakeConnector(cid, [ToolSchema(name="ping", description="", parameters={"type": "object"})])
        connectors.register(c)

    auditor = Auditor(InMemoryAuditSink())
    deps = AgentDeps(
        router=router,
        connectors=connectors,
        policies=PolicyEngine([]),
        auditor=auditor,
    )

    src = (
        '[{"text":"x","sources":[{"connector":"c","tool":"t","ref":"r","ts":"2026-05-17T00:00:00+00:00"}]}]'
    )
    # Each specialist makes one direct call (no tools) and returns a digest:
    fake_llm.enqueue(
        _ok_completion(
            '{"yesterday_outcomes":' + src + ',"today_prep":[],"action_items":[]}'
        )
    )
    fake_llm.enqueue(
        _ok_completion(
            '{"watchlist_deltas":' + src + ',"macro_signal":[],"new_filings":[]}'
        )
    )
    fake_llm.enqueue(
        _ok_completion('{"topic_deltas":' + src + ',"deep_dive":[]}')
    )

    specialists = {
        "meetings": MeetingsAgent(_agent_cfg("meetings", "gcal"), deps),
        "markets": MarketsAgent(_agent_cfg("markets", "polygon"), deps),
        "research": ResearchAgent(_agent_cfg("research", "exa_search"), deps),
    }
    director = Director(deps=deps, specialists=specialists)

    user = User(
        id="u1",
        tenant_id="acme",
        email="alice@acme.com",
        display_name="Alice",
        timezone="Asia/Kolkata",
        delivery_prefs=DeliveryPrefs(channels=["console"]),
    )
    console = ConsoleChannel()
    memory = FilesystemMemory(tmp_path / "mem")

    brief = await run_morning_brief(
        user=user,
        for_date=date(2026, 5, 17),
        ctx=_ctx(),
        director=director,
        memory=memory,
        auditor=auditor,
        channels={"console": console},
    )

    assert {s.agent for s in brief.sections} == {"meetings", "markets", "research"}
    assert all(s.status == "ok" for s in brief.sections), [
        (s.agent, s.status, s.error) for s in brief.sections
    ]
    assert brief.total_cost_usd > 0
    assert len(console.delivered) == 1

    # Memory handoff was persisted
    handoff = memory.read("acme", "u1", "yesterday_brief.md")
    assert handoff is not None and "Brief for 2026-05-17" in handoff

    # Audit recorded the brief generation event
    kinds = [ev.kind for ev, _ in auditor._sink.events]  # type: ignore[attr-defined]
    assert "brief.generated" in kinds


@pytest.mark.asyncio
async def test_kill_switch_skips_specialist():
    fake_llm = FakeLLMProvider()
    reg = LLMRegistry()
    reg.register("fake", lambda: fake_llm)
    router = LLMRouter(registry=reg)
    connectors = ConnectorRegistry()
    connectors.register(FakeConnector("gcal", [ToolSchema(name="ping", description="", parameters={})]))
    connectors.register(FakeConnector("exa_search", [ToolSchema(name="ping", description="", parameters={})]))
    auditor = Auditor(InMemoryAuditSink())
    deps = AgentDeps(router=router, connectors=connectors, policies=PolicyEngine([]), auditor=auditor)

    src = '[{"text":"x","sources":[{"connector":"c","tool":"t","ref":"r","ts":"2026-05-17T00:00:00+00:00"}]}]'
    fake_llm.enqueue(
        _ok_completion(
            '{"yesterday_outcomes":' + src + ',"today_prep":[],"action_items":[]}'
        )
    )

    specialists = {
        "meetings": MeetingsAgent(_agent_cfg("meetings", "gcal"), deps),
        "research": ResearchAgent(_agent_cfg("research", "exa_search"), deps),
    }
    director = Director(deps=deps, specialists=specialists)
    from avengers.agents.director import DirectorInput

    brief = await director.run_morning(
        DirectorInput(
            user_id="u1",
            tenant_id="acme",
            for_date=date(2026, 5, 17),
            agents=["meetings", "research"],
            kill_switched=["research"],
        ),
        _ctx(),
    )
    assert {s.agent for s in brief.sections} == {"meetings"}
    assert brief.kill_switched == ["research"]


@pytest.mark.asyncio
async def test_specialist_error_is_isolated():
    """One specialist's failure does not poison the others."""
    fake_llm = FakeLLMProvider()
    reg = LLMRegistry()
    reg.register("fake", lambda: fake_llm)
    router = LLMRouter(registry=reg)
    connectors = ConnectorRegistry()
    connectors.register(FakeConnector("gcal", [ToolSchema(name="ping", description="", parameters={})]))
    connectors.register(FakeConnector("polygon", [ToolSchema(name="ping", description="", parameters={})]))
    auditor = Auditor(InMemoryAuditSink())
    deps = AgentDeps(router=router, connectors=connectors, policies=PolicyEngine([]), auditor=auditor)

    src = '[{"text":"x","sources":[{"connector":"c","tool":"t","ref":"r","ts":"2026-05-17T00:00:00+00:00"}]}]'
    # meetings: good digest
    fake_llm.enqueue(
        _ok_completion('{"yesterday_outcomes":' + src + ',"today_prep":[],"action_items":[]}')
    )
    # markets: invalid JSON — parse error
    fake_llm.enqueue(_ok_completion("not json at all"))

    specialists = {
        "meetings": MeetingsAgent(_agent_cfg("meetings", "gcal"), deps),
        "markets": MarketsAgent(_agent_cfg("markets", "polygon"), deps),
    }
    director = Director(deps=deps, specialists=specialists)
    from avengers.agents.director import DirectorInput

    brief = await director.run_morning(
        DirectorInput(
            user_id="u1",
            tenant_id="acme",
            for_date=date(2026, 5, 17),
            agents=["meetings", "markets"],
        ),
        _ctx(),
    )
    statuses = {s.agent: s.status for s in brief.sections}
    assert statuses["meetings"] == "ok"
    assert statuses["markets"] == "error"

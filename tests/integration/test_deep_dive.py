from datetime import date

from avengers.agents.base import AgentDeps
from avengers.agents.research import ResearchAgent
from avengers.connectors.base import ConnectorRegistry
from avengers.connectors.fake_connector import FakeConnector
from avengers.core.audit import Auditor, InMemoryAuditSink
from avengers.core.policy import PolicyEngine
from avengers.core.tenant import TenantContext
from avengers.llm.base import LLMRegistry
from avengers.llm.fake_provider import FakeLLMProvider
from avengers.llm.router import LLMRouter
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
from avengers.schemas.llm import Completion, ToolSchema
from avengers.workflows.deep_dive import run_deep_dive


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


async def test_deep_dive_returns_cited_answer():
    fake = FakeLLMProvider()
    reg = LLMRegistry()
    reg.register("fake", lambda: fake)
    router = LLMRouter(registry=reg)
    connectors = ConnectorRegistry()
    connectors.register(FakeConnector("exa_search", [ToolSchema(name="search", description="", parameters={})]))
    deps = AgentDeps(
        router=router,
        connectors=connectors,
        policies=PolicyEngine([]),
        auditor=Auditor(InMemoryAuditSink()),
    )

    src = '[{"text":"answer","sources":[{"connector":"exa_search","tool":"search","ref":"u","ts":"2026-05-17T00:00:00+00:00"}]}]'
    fake.enqueue(
        Completion(
            model="m1",
            output_text='{"topic_deltas":[],"deep_dive":' + src + '}',
            stop_reason="end_turn",
            cost_usd=0.001,
        )
    )
    cfg = AgentConfig(
        id="research",
        display_name="Research",
        version="0.1.0",
        model=ModelCfg(primary="fake:m1"),
        prompt="prompts/research.md",
        input_schema="ResearchInput",
        output_schema="ResearchDigest",
        tools=ToolsCfg(mcp=["exa_search"]),
        limits=LimitsCfg(max_turns=2, wallclock_seconds=5),
    )
    agent = ResearchAgent(cfg, deps)
    result = await run_deep_dive(
        agent=agent, query="why are agents useful?", user_id="u1", ctx=_ctx()
    )
    assert result.query == "why are agents useful?"
    assert len(result.answer) == 1
    assert result.answer[0].sources[0].tool == "search"

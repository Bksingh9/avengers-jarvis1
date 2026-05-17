"""End-to-end agent loop: FakeLLM scripts the tool-use → final-answer dance."""

from __future__ import annotations

from datetime import UTC, date, datetime

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
    PolicyConfig,
    TenantConfig,
    ToolsCfg,
)
from avengers.schemas.llm import Completion, ToolCall, ToolSchema


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


def _agent_cfg() -> AgentConfig:
    return AgentConfig(
        id="research",
        display_name="Research",
        version="0.1.0",
        model=ModelCfg(primary="fake:m1"),
        prompt="prompts/research.md",
        input_schema="ResearchInput",
        output_schema="ResearchDigest",
        tools=ToolsCfg(mcp=["exa_search"]),
        limits=LimitsCfg(max_turns=4, wallclock_seconds=5),
        policies=["no_pii_to_external_search"],
    )


def _wiring():
    fake_llm = FakeLLMProvider()
    reg = LLMRegistry()
    reg.register("fake", lambda: fake_llm)
    router = LLMRouter(registry=reg)

    connectors = ConnectorRegistry()
    exa = FakeConnector(
        "exa_search",
        tools=[ToolSchema(name="search", description="web search", parameters={"type": "object"})],
    )

    async def search_handler(args, ctx):
        return [{"title": "AI agents in 2026", "url": "https://example.com/a"}]

    exa.enqueue("search", search_handler)
    connectors.register(exa)

    policies = PolicyEngine(
        [
            PolicyConfig(
                id="no_pii_to_external_search",
                when="pre_tool",
                match={"tool.name": {"in": ["exa_search.search"]}},
                condition="contains_pii",
                action="deny",
            )
        ]
    )
    auditor = Auditor(InMemoryAuditSink())
    deps = AgentDeps(router=router, connectors=connectors, policies=policies, auditor=auditor)
    return fake_llm, exa, auditor.sink if hasattr(auditor, "sink") else None, deps  # type: ignore[attr-defined]


async def test_two_turn_loop_calls_tool_then_emits_digest():
    fake_llm, _exa, _sink, deps = _wiring()

    # Turn 1: model decides to call exa_search.search
    fake_llm.enqueue(
        Completion(
            model="m1",
            output_text="",
            tool_calls=[
                ToolCall(id="call_1", name="exa_search.search", arguments={"query": "ai agents 2026"})
            ],
            stop_reason="tool_use",
            input_tokens=100,
            output_tokens=20,
            cost_usd=0.001,
        )
    )
    # Turn 2: model produces the final JSON digest
    digest_json = (
        '{"topic_deltas":'
        '[{"text":"AI agents are hot",'
        '"sources":[{"connector":"exa_search","tool":"search","ref":"https://example.com/a","ts":"2026-05-17T00:00:00+00:00"}],'
        '"confidence":0.9}],'
        '"deep_dive":[]}'
    )
    fake_llm.enqueue(
        Completion(
            model="m1",
            output_text=digest_json,
            stop_reason="end_turn",
            input_tokens=200,
            output_tokens=80,
            cost_usd=0.002,
        )
    )
    agent = ResearchAgent(_agent_cfg(), deps)
    result = await agent.run(
        input_payload={"trigger": "morning", "user_id": "u1", "for_date": date(2026, 5, 17).isoformat()},
        ctx=_ctx(),
    )

    assert result.status == "ok", result.error
    assert result.tool_calls == 1
    assert result.output is not None
    assert len(result.output.topic_deltas) == 1
    assert result.output.topic_deltas[0].sources[0].connector == "exa_search"
    assert result.cost_usd > 0


async def test_pii_in_query_is_denied_and_model_sees_error():
    fake_llm, _exa, _sink, deps = _wiring()

    # Model first tries a query with PII — should be denied
    fake_llm.enqueue(
        Completion(
            model="m1",
            tool_calls=[
                ToolCall(id="c1", name="exa_search.search", arguments={"query": "find alice@example.com"})
            ],
            stop_reason="tool_use",
            input_tokens=80,
            output_tokens=10,
            cost_usd=0.0005,
        )
    )
    # Model recovers and emits an empty digest
    fake_llm.enqueue(
        Completion(
            model="m1",
            output_text='{"topic_deltas":[],"deep_dive":[]}',
            stop_reason="end_turn",
            input_tokens=50,
            output_tokens=10,
            cost_usd=0.0005,
        )
    )
    agent = ResearchAgent(_agent_cfg(), deps)
    result = await agent.run(input_payload={}, ctx=_ctx())
    assert result.status == "ok"
    # The tool call was blocked — there should still be one tool_call recorded
    assert result.tool_calls == 1
    # The connector should NOT have been hit
    # (FakeConnector records calls on invoke; deny short-circuits before invoke)
    assert _exa.calls == []


async def test_max_turns_exceeded():
    fake_llm, _exa, _sink, deps = _wiring()
    cfg = _agent_cfg()
    cfg = cfg.model_copy(update={"limits": LimitsCfg(max_turns=2, wallclock_seconds=5)})
    # Two turns of tool_use, never resolves to end_turn
    for _ in range(3):
        fake_llm.enqueue(
            Completion(
                model="m1",
                tool_calls=[ToolCall(id="x", name="exa_search.search", arguments={"query": "ok"})],
                stop_reason="tool_use",
                cost_usd=0.0001,
            )
        )
    agent = ResearchAgent(cfg, deps)
    result = await agent.run(input_payload={}, ctx=_ctx())
    assert result.status == "error"
    assert result.error == "max_turns_exceeded"

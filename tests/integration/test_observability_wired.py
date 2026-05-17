"""Prove metrics + tracing + LLM trace sink fire during a real agent run."""

from __future__ import annotations

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
from avengers.observability.langfuse_sink import NullLLMTraceSink, set_sink
from avengers.observability.metrics import InMemoryMetrics, NullMetrics, set_metrics
from avengers.observability.tracing import NullTracer, RecordingTracer, set_tracer
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


def _cfg() -> AgentConfig:
    return AgentConfig(
        id="research",
        display_name="Research",
        version="0.1.0",
        model=ModelCfg(primary="fake:m1"),
        prompt="prompts/research.md",
        input_schema="x",
        output_schema="y",
        tools=ToolsCfg(mcp=["exa_search"]),
        limits=LimitsCfg(max_turns=3, wallclock_seconds=5),
    )


async def test_metrics_fire_on_llm_and_tool_calls(monkeypatch):
    metrics = InMemoryMetrics()
    tracer = RecordingTracer()
    sink = NullLLMTraceSink()
    set_metrics(metrics)
    set_tracer(tracer)
    set_sink(sink)
    monkeypatch.setattr(
        "avengers.llm.router.get_sink",
        lambda: sink,
    )
    try:
        fake = FakeLLMProvider()
        reg = LLMRegistry()
        reg.register("fake", lambda: fake)
        connectors = ConnectorRegistry()
        exa = FakeConnector("exa_search", [ToolSchema(name="search", description="", parameters={})])

        async def _handler(args, ctx):
            return [{"title": "x"}]

        exa.enqueue("search", _handler)
        connectors.register(exa)

        fake.enqueue(
            Completion(
                model="m1",
                tool_calls=[ToolCall(id="c1", name="exa_search.search", arguments={"q": "ai"})],
                stop_reason="tool_use",
                input_tokens=100,
                output_tokens=10,
                cost_usd=0.001,
            )
        )
        src = '[{"text":"x","sources":[{"connector":"c","tool":"t","ref":"r","ts":"2026-05-17T00:00:00+00:00"}]}]'
        fake.enqueue(
            Completion(
                model="m1",
                output_text='{"topic_deltas":' + src + ',"deep_dive":[]}',
                stop_reason="end_turn",
                input_tokens=200,
                output_tokens=80,
                cost_usd=0.002,
            )
        )

        deps = AgentDeps(
            router=LLMRouter(registry=reg),
            connectors=connectors,
            policies=PolicyEngine([]),
            auditor=Auditor(InMemoryAuditSink()),
        )
        agent = ResearchAgent(_cfg(), deps)
        result = await agent.run(
            input_payload={"trigger": "morning", "user_id": "u1", "for_date": date(2026, 5, 17).isoformat()},
            ctx=_ctx(),
        )
        assert result.status == "ok"

        # LLM-level metrics fired twice (two turns):
        llm_labels = {"provider": "fake", "model": "m1", "tenant": "acme"}
        assert metrics.counter("llm.calls", llm_labels) == 2.0
        assert metrics.counter("llm.input_tokens", llm_labels) == 300.0
        assert metrics.counter("llm.output_tokens", llm_labels) == 90.0
        assert metrics.counter("llm.cost_usd", llm_labels) == 0.003

        # Tool-level metrics fired once:
        tool_labels = {"agent": "research", "tenant": "acme", "tool": "exa_search.search"}
        assert metrics.counter("tool.invocations", tool_labels) == 1.0
        assert metrics.counter("tool.errors", tool_labels) == 0.0

        # Agent-level metrics:
        agent_labels = {"agent": "research", "tenant": "acme"}
        assert metrics.counter("agent.runs", agent_labels) == 1.0
        assert metrics.counter("agent.status.ok", agent_labels) == 1.0

        # Tracer saw spans for both LLM calls and the tool invoke
        opened_names = [n for n, _ in tracer.opened]
        assert opened_names.count("llm.call") == 2
        assert opened_names.count("tool.invoke") == 1

        # LLM trace sink captured both calls
        traces = list(sink.recorded)
        assert len(traces) == 2
        assert traces[0].provider == "fake"
        assert traces[0].model == "m1"
        assert traces[0].input_tokens == 100
    finally:
        set_metrics(NullMetrics())
        set_tracer(NullTracer())
        set_sink(NullLLMTraceSink())

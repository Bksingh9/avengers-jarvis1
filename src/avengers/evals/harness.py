"""Eval-suite harness.

Drives an agent against scripted FakeLLM responses + scripted FakeConnector
handlers, scores each outcome with named scorers, and returns a pass/fail
aggregate gated by the agent's configured threshold.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from avengers.agents.base import AgentDeps, AgentResult, BaseAgent
from avengers.connectors.base import ConnectorRegistry
from avengers.connectors.fake_connector import FakeConnector
from avengers.core.audit import Auditor, InMemoryAuditSink
from avengers.core.policy import PolicyEngine
from avengers.core.tenant import TenantContext
from avengers.llm.base import LLMRegistry
from avengers.llm.fake_provider import FakeLLMProvider
from avengers.llm.router import LLMRouter
from avengers.schemas.brief import Cited
from avengers.schemas.config import (
    AgentConfig,
    AuditCfg,
    BudgetCfg,
    IdentityCfg,
    LLMRoutingCfg,
    TenantConfig,
)
from avengers.schemas.llm import Completion, ToolSchema

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Case schema
# ---------------------------------------------------------------------------


class EvalPredicate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scorer: str
    args: dict[str, Any] = Field(default_factory=dict)


class EvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    description: str = ""
    input: dict[str, Any] = Field(default_factory=dict)
    scripted_llm_responses: list[dict[str, Any]] = Field(default_factory=list)
    scripted_tool_responses: dict[str, Any] = Field(default_factory=dict)
    # ^ key format: "<connector>.<tool>" → value to return
    connectors: list[str] = Field(default_factory=list)
    predicates: list[EvalPredicate] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Scorer registry
# ---------------------------------------------------------------------------


Scorer = Callable[[AgentResult[Any], EvalCase, dict[str, Any]], bool]
scorer_registry: dict[str, Scorer] = {}


def register_scorer(name: str) -> Callable[[Scorer], Scorer]:
    def deco(fn: Scorer) -> Scorer:
        if name in scorer_registry:
            raise ValueError(f"scorer already registered: {name}")
        scorer_registry[name] = fn
        return fn

    return deco


@register_scorer("output_parses")
def _s_output_parses(result, case, args):  # type: ignore[no-untyped-def]
    return result.output is not None and result.status in {"ok", "partial"}


@register_scorer("no_errors")
def _s_no_errors(result, case, args):  # type: ignore[no-untyped-def]
    return result.status == "ok" and result.error is None


@register_scorer("all_claims_cited")
def _s_all_cited(result, case, args):  # type: ignore[no-untyped-def]
    if result.output is None:
        return False
    for v in _walk_values(result.output):
        if isinstance(v, Cited) and not v.sources:
            return False
    return True


@register_scorer("cost_under")
def _s_cost_under(result, case, args):  # type: ignore[no-untyped-def]
    cap = float(args.get("usd", 1.0))
    return result.cost_usd <= cap


@register_scorer("latency_under")
def _s_latency_under(result, case, args):  # type: ignore[no-untyped-def]
    cap = int(args.get("ms", 60_000))
    return result.latency_ms <= cap


@register_scorer("tool_called")
def _s_tool_called(result, case, args):  # type: ignore[no-untyped-def]
    """Pass if at least N tool calls were made (default 1)."""
    return result.tool_calls >= int(args.get("min", 1))


def _walk_values(obj: Any):
    if isinstance(obj, Cited):
        yield obj
        return
    if hasattr(obj, "model_dump"):
        for v in obj.model_dump().values():
            yield from _walk_values(v)
        return
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _walk_values(v)
        return
    if isinstance(obj, list | tuple):
        for v in obj:
            yield from _walk_values(v)


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class EvalCaseResult:
    case_id: str
    passed: bool
    failed_predicates: list[str]
    cost_usd: float
    latency_ms: int
    error: str | None = None


@dataclass(slots=True)
class EvalReport:
    agent_id: str
    cases: list[EvalCaseResult] = field(default_factory=list)

    @property
    def score(self) -> float:
        if not self.cases:
            return 0.0
        return sum(1 for c in self.cases if c.passed) / len(self.cases)

    def gate(self, threshold: float) -> bool:
        return self.score >= threshold


def _default_ctx() -> TenantContext:
    return TenantContext(
        tenant=TenantConfig(
            id="eval",
            name="Eval",
            region="us",
            identity=IdentityCfg(provider="oidc", issuer="https://x"),
            secrets_namespace="ns",
            kms_key_arn="arn",
            audit=AuditCfg(bucket="b"),
            budgets=BudgetCfg(daily_usd_cap=100, per_user_usd_cap=10),
            llm_routing=LLMRoutingCfg(default="fake:m1"),
        )
    )


@dataclass(slots=True)
class EvalHarness:
    agent_cls: type[BaseAgent[Any]]
    agent_config: AgentConfig
    cases: list[EvalCase]
    policies: list = field(default_factory=list)  # type: ignore[type-arg]

    @classmethod
    def from_glob(
        cls,
        *,
        agent_cls: type[BaseAgent[Any]],
        agent_config: AgentConfig,
        cases_glob: str,
    ) -> "EvalHarness":
        paths = sorted(Path().glob(cases_glob))
        cases = [EvalCase.model_validate(yaml.safe_load(p.read_text())) for p in paths]
        return cls(agent_cls=agent_cls, agent_config=agent_config, cases=cases)

    async def run_one(self, case: EvalCase) -> EvalCaseResult:
        fake_llm = FakeLLMProvider()
        for spec in case.scripted_llm_responses:
            fake_llm.enqueue(Completion.model_validate(spec))
        reg = LLMRegistry()
        reg.register("fake", lambda: fake_llm)
        reg.register("anthropic", lambda: fake_llm)
        router = LLMRouter(registry=reg)

        connectors = ConnectorRegistry()
        for cid in case.connectors or self.agent_config.tools.mcp:
            c = FakeConnector(
                cid, [ToolSchema(name="search", description="", parameters={"type": "object"})]
            )
            for key, value in case.scripted_tool_responses.items():
                con_id, _, tool_name = key.partition(".")
                if con_id != cid:
                    continue

                async def _handler(_args, _ctx, _v=value):  # noqa: ANN001
                    return _v

                c.enqueue(tool_name or "search", _handler)
            connectors.register(c)

        deps = AgentDeps(
            router=router,
            connectors=connectors,
            policies=PolicyEngine(self.policies),
            auditor=Auditor(InMemoryAuditSink()),
        )
        agent = self.agent_cls(self.agent_config, deps)
        result = await agent.run(input_payload=case.input, ctx=_default_ctx())

        failed: list[str] = []
        for pred in case.predicates:
            scorer = scorer_registry.get(pred.scorer)
            if scorer is None:
                failed.append(f"{pred.scorer}:unregistered")
                continue
            try:
                ok = scorer(result, case, pred.args)
            except Exception as exc:  # noqa: BLE001
                failed.append(f"{pred.scorer}:{exc}")
                continue
            if not ok:
                failed.append(pred.scorer)
        return EvalCaseResult(
            case_id=case.id,
            passed=not failed,
            failed_predicates=failed,
            cost_usd=result.cost_usd,
            latency_ms=result.latency_ms,
            error=result.error,
        )

    async def run_all(self) -> EvalReport:
        report = EvalReport(agent_id=self.agent_config.id)
        for case in self.cases:
            report.cases.append(await self.run_one(case))
        return report

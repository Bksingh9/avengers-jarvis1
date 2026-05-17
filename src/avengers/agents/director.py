"""Director (spec §10.1).

Fans out to enabled specialists in parallel and aggregates their digests into
a `MorningBrief`. Best-effort: any specialist that errors becomes a Section
with status="error" — the brief is delivered with what succeeded.

The Director does NOT run an LLM loop itself in v1; orchestration is
deterministic Python. This keeps the morning-brief workflow cheap and
predictable. The LLM enters via each specialist's `BaseAgent.run`.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from avengers.agents.base import AgentDeps, BaseAgent
from avengers.core.tenant import TenantContext
from avengers.schemas.brief import Decision, MorningBrief, Section

logger = logging.getLogger(__name__)

Trigger = Literal["morning", "on_demand"]


class DirectorInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    tenant_id: str
    for_date: date
    trigger: Trigger = "morning"
    query: str | None = None
    # which agents to run; defaults to tenant.agents_enabled
    agents: list[str] = Field(default_factory=list)
    # kill_switched agents are skipped and recorded in the brief
    kill_switched: list[str] = Field(default_factory=list)


@dataclass(slots=True)
class Director:
    deps: AgentDeps
    specialists: dict[str, BaseAgent[Any]]

    async def run_morning(self, input_: DirectorInput, ctx: TenantContext) -> MorningBrief:
        t0 = time.monotonic()
        # Honour the tenant's `agents_enabled` list — the Director holds every
        # specialist class the platform knows, but a tenant only runs its
        # configured subset. Callers can also pass `input_.agents` to override.
        tenant_enabled = set(ctx.tenant.agents_enabled)
        enabled = input_.agents or [a for a in self.specialists if a in tenant_enabled]
        to_run = [a for a in enabled if a not in input_.kill_switched and a in self.specialists]
        skipped = [a for a in enabled if a in input_.kill_switched]

        results = await asyncio.gather(
            *[self._run_one(name, input_, ctx) for name in to_run],
            return_exceptions=True,
        )

        sections: list[Section] = []
        total_cost = 0.0
        decisions: list[Decision] = []
        model_versions: dict[str, str] = {}

        for name, outcome in zip(to_run, results, strict=True):
            if isinstance(outcome, BaseException):
                sections.append(
                    Section(
                        agent=name,
                        status="error",
                        digest={},
                        latency_ms=0,
                        cost_usd=0.0,
                        error=str(outcome),
                    )
                )
                continue
            agent_result, agent_cfg = outcome
            total_cost += agent_result.cost_usd
            model_versions[name] = agent_cfg.model.primary
            digest_dump: dict[str, Any] = {}
            if agent_result.output is not None:
                digest_dump = agent_result.output.model_dump(mode="json")
                # Promote any embedded Decision-like items here in v1.1.
            sections.append(
                Section(
                    agent=name,
                    status=agent_result.status,  # type: ignore[arg-type]
                    digest=digest_dump,
                    latency_ms=agent_result.latency_ms,
                    cost_usd=agent_result.cost_usd,
                    error=agent_result.error,
                )
            )

        # Rank: irreversible > high_cost > reversible, then by nearest deadline
        decisions.sort(
            key=lambda d: (
                {"irreversible": 0, "high_cost": 1, "reversible": 2}[d.reversibility],
                d.deadline or datetime.max.replace(tzinfo=UTC),
            )
        )

        brief = MorningBrief(
            tenant_id=ctx.tenant_id,
            user_id=input_.user_id,
            for_date=input_.for_date,
            decisions_today=decisions,
            sections=sections,
            kill_switched=skipped,
            generated_at=datetime.now(UTC),
            model_versions=model_versions,
            total_cost_usd=total_cost,
        )
        latency_ms = int((time.monotonic() - t0) * 1000)
        logger.info(
            "morning_brief tenant=%s user=%s latency_ms=%d cost=%.4f sections=%d",
            ctx.tenant_id,
            input_.user_id,
            latency_ms,
            total_cost,
            len(sections),
        )
        return brief

    async def _run_one(self, name: str, input_: DirectorInput, ctx: TenantContext):
        agent = self.specialists[name]
        payload = {
            "user_id": input_.user_id,
            "for_date": input_.for_date.isoformat(),
            "trigger": input_.trigger,
            "query": input_.query,
        }
        result = await agent.run(input_payload=payload, ctx=ctx)
        return result, agent.config

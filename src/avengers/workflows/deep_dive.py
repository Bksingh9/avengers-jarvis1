"""Deep-dive workflow (spec §11.2).

A single specialist run keyed by `trigger="on_demand"`. Default routes to the
Research agent unless the caller picks another one. Returns a `DeepDiveResult`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from avengers.agents.base import BaseAgent
from avengers.core.tenant import TenantContext
from avengers.schemas.brief import Cited, DeepDiveResult, Source


async def run_deep_dive(
    *,
    agent: BaseAgent[Any],
    query: str,
    user_id: str,
    ctx: TenantContext,
) -> DeepDiveResult:
    result = await agent.run(
        input_payload={"trigger": "on_demand", "query": query, "user_id": user_id},
        ctx=ctx,
    )
    answer_items: list[Cited] = []
    if result.output is not None:
        for v in result.output.model_dump(mode="json").values():
            if isinstance(v, list):
                for item in v:
                    if isinstance(item, dict) and "text" in item and item.get("sources"):
                        answer_items.append(Cited.model_validate(item))
    if not answer_items and result.raw_text:
        # No structured output — fall back to a single agent-cited claim so the
        # `Cited` invariant still holds.
        answer_items = [
            Cited(
                text=result.raw_text,
                sources=[
                    Source(
                        connector="agent",
                        tool=agent.config.id,
                        ref="raw",
                        ts=datetime.now(UTC),
                    )
                ],
                confidence=0.4,
            )
        ]
    return DeepDiveResult(
        tenant_id=ctx.tenant_id,
        user_id=user_id,
        query=query,
        answer=answer_items,
        generated_at=datetime.now(UTC),
        total_cost_usd=result.cost_usd,
    )

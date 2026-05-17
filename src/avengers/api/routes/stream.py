"""POST /tenants/{id}/briefs/stream — Server-Sent Events progress feed.

Emits one `event: section` per specialist as it finishes, plus a final
`event: done` carrying the full MorningBrief. The dashboard consumes this so
the brief renders progressively instead of as a 30-second wait.
"""

from __future__ import annotations

import asyncio
import json
from datetime import date
from typing import Annotated, AsyncIterator

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from avengers.agents.director import DirectorInput
from avengers.api.app import AppContainer
from avengers.api.deps import get_container, require_tenant_ctx
from avengers.core.tenant import TenantContext

router = APIRouter(prefix="/tenants/{tenant_id}/briefs", tags=["briefs"])


class StreamBriefRequest(BaseModel):
    for_date: date | None = None


def _sse(event: str, data: dict | list | str) -> str:
    body = json.dumps(data, default=str) if not isinstance(data, str) else data
    return f"event: {event}\ndata: {body}\n\n"


@router.post("/stream", status_code=status.HTTP_200_OK)
async def stream(
    body: StreamBriefRequest,
    ctx: Annotated[TenantContext, Depends(require_tenant_ctx)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> StreamingResponse:
    assert ctx.user is not None
    target_date = body.for_date or date.today()
    director = container.director
    # Only stream the specialists this tenant has enabled. The Director holds
    # every registered specialist class; tenants pick their subset in YAML.
    tenant_enabled = set(ctx.tenant.agents_enabled)
    enabled = [a for a in director.specialists if a in tenant_enabled]

    # Per-section queue so we can stream as each completes.
    queue: asyncio.Queue[tuple[str, dict] | None] = asyncio.Queue()

    async def run_section(name: str) -> None:
        agent = director.specialists[name]
        result = await agent.run(
            input_payload={
                "user_id": ctx.user.id,  # type: ignore[union-attr]
                "for_date": target_date.isoformat(),
                "trigger": "morning",
            },
            ctx=ctx,
        )
        digest = result.output.model_dump(mode="json") if result.output is not None else {}
        await queue.put(
            (
                "section",
                {
                    "agent": name,
                    "status": result.status,
                    "digest": digest,
                    "cost_usd": result.cost_usd,
                    "latency_ms": result.latency_ms,
                    "error": result.error,
                },
            )
        )

    async def runner() -> None:
        tasks = [asyncio.create_task(run_section(n)) for n in enabled]
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            await queue.put(None)

    async def event_gen() -> AsyncIterator[str]:
        yield _sse(
            "start",
            {"for_date": target_date.isoformat(), "agents": enabled, "tenant": ctx.tenant_id},
        )
        runner_task = asyncio.create_task(runner())
        sections: list[dict] = []
        total_cost = 0.0
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                _, payload = item
                sections.append(payload)
                total_cost += float(payload.get("cost_usd", 0.0))
                yield _sse("section", payload)
            yield _sse(
                "done",
                {
                    "for_date": target_date.isoformat(),
                    "sections": sections,
                    "total_cost_usd": total_cost,
                },
            )
        finally:
            await runner_task

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )

"""JARVIS conversational + proactive endpoints (Cap Brij persona).

Two routes:

* POST /tenants/{id}/jarvis/converse — single-turn deep-dive routed to the
  research specialist with the JARVIS persona overlay active. Returns text
  shaped for TTS playback: short sentences, no markdown, no JSON.

* POST /tenants/{id}/jarvis/proactive — triggered by Vercel cron (header
  `Authorization: Bearer ${CRON_SECRET}`) or by the dashboard. Runs the
  morning brief and returns a one-paragraph push payload suitable for
  Telegram / browser notification / "Cap Brij — here's what you need to
  know now" preview cards.
"""

from __future__ import annotations

import os
import re
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, status
from pydantic import BaseModel, Field

from avengers.agents.director import DirectorInput
from avengers.api.app import AppContainer
from avengers.api.deps import get_container, require_tenant_ctx
from avengers.core.tenant import TenantContext
from avengers.schemas.identity import User
from avengers.workflows.deep_dive import run_deep_dive

router = APIRouter(prefix="/tenants/{tenant_id}/jarvis", tags=["jarvis"])


class ConverseRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2_000)
    voice_mode: bool = True


class ConverseResponse(BaseModel):
    text: str
    speakable: str
    cost_usd: float
    citations: list[dict] = Field(default_factory=list)


class ProactiveResponse(BaseModel):
    headline: str
    body: str
    speakable: str
    sections: list[dict]
    total_cost_usd: float


def _strip_for_tts(s: str) -> str:
    """Markdown / fences / brackets confuse browser TTS. Strip them."""
    s = re.sub(r"```[\s\S]*?```", " ", s)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    s = re.sub(r"[*_#>~|]", "", s)
    s = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


@router.post("/converse", response_model=ConverseResponse)
async def converse(
    body: ConverseRequest,
    ctx: Annotated[TenantContext, Depends(require_tenant_ctx)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> ConverseResponse:
    """Single-turn deep-dive. Routes through the research specialist so the
    cite_every_claim policy still applies. The persona overlay registered for
    the `jarvis` tenant makes the agent address the user as Cap Brij."""
    if "research" not in container.director.specialists:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="research specialist not enabled for this tenant",
        )
    research = container.director.specialists["research"]
    assert ctx.user is not None
    result = await run_deep_dive(
        agent=research,
        query=body.query,
        user_id=ctx.user.id,
        ctx=ctx,
    )
    text = " ".join(c.text for c in result.answer) or "Nothing to report, Cap Brij."
    speakable = _strip_for_tts(text)
    citations = [
        {"connector": s.connector, "tool": s.tool, "ref": s.ref}
        for c in result.answer
        for s in c.sources
    ]
    return ConverseResponse(
        text=text,
        speakable=speakable,
        cost_usd=result.total_cost_usd,
        citations=citations,
    )


async def _require_user_or_cron(
    tenant_id: Annotated[str, Path(pattern=r"^[a-z0-9_-]+$")],
    container: Annotated[AppContainer, Depends(get_container)],
    authorization: Annotated[str | None, Header()] = None,
    x_cron_secret: Annotated[str | None, Header()] = None,
) -> TenantContext:
    """Dashboard calls this with a user bearer (Authorization header). Vercel
    Cron calls it with `X-Cron-Secret`. Either path resolves to a
    TenantContext for the addressed tenant.

    `CRON_SECRET=...` in the backend env enables the cron path; unset means
    user-only (dev default).
    """
    cron_secret = os.getenv("CRON_SECRET")
    if cron_secret and x_cron_secret == cron_secret:
        try:
            tenant = container.config_store.tenant(tenant_id)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown tenant") from exc
        system_user = User(
            id="system:cron",
            tenant_id=tenant_id,
            email="cron@example.com",
            display_name="System Cron",
            groups={"avengers-admin", "jarvis-owner"},
            timezone=tenant.timezone,
        )
        return TenantContext(tenant=tenant, user=system_user)

    # Fall back to normal user auth.
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="auth required")
    token = authorization.split(" ", 1)[1]
    try:
        user = await container.identity.verify_token(token)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    if user.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="cross-tenant access denied")
    try:
        tenant = container.config_store.tenant(tenant_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown tenant") from exc
    return TenantContext(tenant=tenant, user=user)


@router.post("/proactive", response_model=ProactiveResponse)
async def proactive(
    ctx: Annotated[TenantContext, Depends(_require_user_or_cron)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> ProactiveResponse:
    """Triggered by Vercel Cron (X-Cron-Secret) OR the dashboard (user bearer).
    Generates today's brief and shapes it into a push payload (headline +
    body + speakable). The dashboard uses the same endpoint to show a
    "Cap Brij — here's what you need now" banner."""
    assert ctx.user is not None
    today = date.today()
    brief = await container.director.run_morning(
        DirectorInput(user_id=ctx.user.id, tenant_id=ctx.tenant_id, for_date=today),
        ctx,
    )

    # Pull the top 3 things across sections by walking each digest's first list
    # field. Order: errors first (we need to surface them), then ok sections.
    highlights: list[str] = []
    for sec in sorted(brief.sections, key=lambda s: 0 if s.status == "error" else 1):
        if sec.status == "error":
            highlights.append(f"{sec.agent}: section failed — {sec.error or 'unknown'}")
            continue
        for field_name, value in (sec.digest or {}).items():
            if isinstance(value, list) and value:
                first = value[0]
                if isinstance(first, dict) and "text" in first:
                    highlights.append(f"{sec.agent}: {first['text']}")
                    break
        if len(highlights) >= 3:
            break

    if not highlights:
        headline = "Cap Brij — nothing urgent."
        body = "All sections green. Clear runway."
    else:
        headline = f"Cap Brij — {len(highlights)} thing{'s' if len(highlights) > 1 else ''} for you."
        body = "  ".join(f"• {h}" for h in highlights[:3])

    speakable = _strip_for_tts(f"{headline} {body}")
    return ProactiveResponse(
        headline=headline,
        body=body,
        speakable=speakable,
        sections=[
            {"agent": s.agent, "status": s.status, "cost_usd": s.cost_usd}
            for s in brief.sections
        ],
        total_cost_usd=brief.total_cost_usd,
    )

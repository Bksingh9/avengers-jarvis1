"""JARVIS conversational + proactive endpoints (Cap Brij persona).

Two routes:

* POST /tenants/{id}/jarvis/converse — single-turn deep-dive routed to the
  research specialist with the JARVIS persona overlay active. Falls back
  to a direct OpenAI chat call (with the same persona overlay) when the
  agent loop returns nothing — so JARVIS still answers casual questions
  like "introduce yourself" without needing a tool call.

* POST /tenants/{id}/jarvis/proactive — triggered by Vercel cron (header
  `Authorization: Bearer ${CRON_SECRET}`) or by the dashboard. Runs the
  morning brief and returns a one-paragraph push payload suitable for
  Telegram / browser notification / "Cap Brij — here's what you need to
  know now" preview cards.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path as FPath, status
from pydantic import BaseModel, Field

from avengers.agents.director import DirectorInput
from avengers.api.app import AppContainer
from avengers.api.deps import get_container, require_tenant_ctx
from avengers.core.tenant import TenantContext
from avengers.schemas.identity import User
from avengers.workflows.deep_dive import run_deep_dive

logger = logging.getLogger(__name__)

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


def _load_persona(tenant_id: str) -> str:
    """Best-effort load of memory/<tenant>/persona.md. Falls back to a
    sensible default JARVIS persona if the file isn't present in the
    deployed image. Never raises.
    """
    candidates = [
        Path(__file__).resolve().parents[4] / "memory" / tenant_id / "persona.md",
        Path("/app/memory") / tenant_id / "persona.md",
    ]
    for p in candidates:
        try:
            if p.exists():
                return p.read_text().strip()
        except OSError:
            continue
    if tenant_id == "jarvis":
        return (
            "You are JARVIS, the personal AI assistant for Cap Brij. "
            "You speak in short, calm, confident sentences — like the JARVIS "
            "from the Iron Man films. Address the user as 'Cap Brij'. "
            "Keep replies under three sentences unless asked to elaborate. "
            "Never use markdown — your output is read aloud."
        )
    return ""


async def _direct_openai_reply(query: str, tenant_id: str) -> tuple[str, float]:
    """Direct OpenAI chat call used as a fallback when the agent loop returns
    nothing. Keeps JARVIS conversational for everyday questions while the
    full agent pipeline handles research-style deep-dives.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return ("", 0.0)
    try:
        from openai import AsyncOpenAI
    except ImportError:
        logger.warning("openai SDK not available for fallback")
        return ("", 0.0)

    persona = _load_persona(tenant_id)
    model = os.environ.get("OPENAI_MODEL_DEFAULT", "gpt-4o-mini")
    client = AsyncOpenAI(api_key=api_key)
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": persona or "You are a helpful assistant."},
                {"role": "user", "content": query},
            ],
            max_completion_tokens=400,
            temperature=0.4,
            timeout=20.0,
        )
    except Exception as exc:
        logger.warning("jarvis_openai_fallback_failed err=%s", exc)
        return ("", 0.0)

    text = (resp.choices[0].message.content or "").strip()
    usage = resp.usage
    in_toks = getattr(usage, "prompt_tokens", 0) if usage else 0
    out_toks = getattr(usage, "completion_tokens", 0) if usage else 0
    cost = (in_toks / 1_000_000) * 0.15 + (out_toks / 1_000_000) * 0.60
    return (text, cost)


@router.post("/converse", response_model=ConverseResponse)
async def converse(
    body: ConverseRequest,
    ctx: Annotated[TenantContext, Depends(require_tenant_ctx)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> ConverseResponse:
    """Single-turn deep-dive with a direct-LLM fallback for casual questions."""
    text: str = ""
    citations: list[dict] = []
    cost_usd: float = 0.0

    research = container.director.specialists.get("research")
    if research is not None:
        assert ctx.user is not None
        try:
            result = await run_deep_dive(
                agent=research,
                query=body.query,
                user_id=ctx.user.id,
                ctx=ctx,
            )
            text = " ".join(c.text for c in result.answer).strip()
            citations = [
                {"connector": s.connector, "tool": s.tool, "ref": s.ref}
                for c in result.answer
                for s in c.sources
            ]
            cost_usd = result.total_cost_usd
        except Exception as exc:
            logger.warning("jarvis_deep_dive_failed err=%s", exc)

    if not text:
        fallback_text, fallback_cost = await _direct_openai_reply(
            body.query, ctx.tenant_id
        )
        if fallback_text:
            text = fallback_text
            cost_usd += fallback_cost

    if not text:
        text = "Nothing to report, Cap Brij."

    speakable = _strip_for_tts(text)
    return ConverseResponse(
        text=text,
        speakable=speakable,
        cost_usd=cost_usd,
        citations=citations,
    )


async def _require_user_or_cron(
    tenant_id: Annotated[str, FPath(pattern=r"^[a-z0-9_-]+$")],
    container: Annotated[AppContainer, Depends(get_container)],
    authorization: Annotated[str | None, Header()] = None,
    x_cron_secret: Annotated[str | None, Header()] = None,
) -> TenantContext:
    """Dashboard uses Authorization bearer; Vercel Cron uses X-Cron-Secret."""
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
    """Triggered by Vercel Cron (X-Cron-Secret) OR the dashboard (user bearer)."""
    assert ctx.user is not None
    today = date.today()
    brief = await container.director.run_morning(
        DirectorInput(user_id=ctx.user.id, tenant_id=ctx.tenant_id, for_date=today),
        ctx,
    )

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
        body = " ".join(f"• {h}" for h in highlights[:3])

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

"""Morning-brief workflow (spec §11.1).

Steps:
  1. Resolve TenantContext (caller does this; we accept it).
  2. Pull yesterday's brief + user profile from filesystem memory.
  3. Director fans out specialists in parallel.
  4. Persist the brief; emit one audit event; deliver to every configured channel.

Best-effort: a failure in delivery does not invalidate the brief.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from avengers.agents.director import Director, DirectorInput
from avengers.core.audit import Auditor
from avengers.core.tenant import TenantContext
from avengers.delivery.base import DeliveryChannel
from avengers.memory.fs_memory import FilesystemMemory
from avengers.schemas.brief import MorningBrief
from avengers.schemas.identity import User

logger = logging.getLogger(__name__)


async def run_morning_brief(
    *,
    user: User,
    for_date: date,
    ctx: TenantContext,
    director: Director,
    memory: FilesystemMemory | None,
    auditor: Auditor,
    channels: dict[str, DeliveryChannel],
    channel_configs: dict[str, dict[str, Any]] | None = None,
) -> MorningBrief:
    channel_configs = channel_configs or {}

    yesterday: str | None = None
    profile: str | None = None
    if memory is not None:
        yesterday = memory.read(ctx.tenant_id, user.id, "yesterday_brief.md")
        profile = memory.read(ctx.tenant_id, user.id, "profile.md")
        if yesterday or profile:
            logger.debug(
                "memory_loaded yesterday=%s profile=%s",
                bool(yesterday),
                bool(profile),
            )

    input_ = DirectorInput(
        user_id=user.id,
        tenant_id=ctx.tenant_id,
        for_date=for_date,
        trigger="morning",
    )
    brief = await director.run_morning(input_, ctx)

    await auditor.emit(
        tenant_id=ctx.tenant_id,
        actor=f"user:{user.id}",
        kind="brief.generated",
        target=str(brief.id),
        payload={
            "for_date": for_date.isoformat(),
            "total_cost_usd": brief.total_cost_usd,
            "sections": [
                {"agent": s.agent, "status": s.status, "cost": s.cost_usd}
                for s in brief.sections
            ],
        },
    )

    # Persist tomorrow's "yesterday" handoff
    if memory is not None:
        memory.write(
            ctx.tenant_id,
            user.id,
            "yesterday_brief.md",
            _render_markdown(brief),
        )

    # Deliver — best-effort, per channel
    for ch_id in user.delivery_prefs.channels:
        channel = channels.get(ch_id)
        if channel is None:
            logger.warning("delivery channel not configured: %s", ch_id)
            continue
        try:
            receipt = await channel.deliver(user, brief, channel_configs.get(ch_id, {}))
            logger.info("delivered channel=%s target=%s ref=%s", ch_id, receipt.target, receipt.external_ref)
        except Exception as exc:  # noqa: BLE001
            logger.error("delivery_failed channel=%s error=%s", ch_id, exc)
            await auditor.emit(
                tenant_id=ctx.tenant_id,
                actor=f"user:{user.id}",
                kind="delivery.error",
                target=ch_id,
                payload={"error": str(exc), "brief_id": str(brief.id)},
                severity="warn",
            )

    return brief


def _render_markdown(brief: MorningBrief) -> str:
    """Compact markdown rendering for the next-day handoff. Pretty rendering
    for human channels is each delivery adapter's responsibility."""
    lines: list[str] = [f"# Brief for {brief.for_date.isoformat()}", ""]
    for s in brief.sections:
        lines.append(f"## {s.agent} [{s.status}]")
        if s.error:
            lines.append(f"_error: {s.error}_")
        for k, v in (s.digest or {}).items():
            lines.append(f"- **{k}**: {v}")
        lines.append("")
    return "\n".join(lines)

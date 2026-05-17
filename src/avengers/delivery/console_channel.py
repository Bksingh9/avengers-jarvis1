"""Dev/test delivery channel — buffers briefs in memory instead of sending."""

from __future__ import annotations

from datetime import UTC, datetime

from avengers.delivery.base import DeliveryChannel, DeliveryReceipt
from avengers.schemas.brief import MorningBrief
from avengers.schemas.identity import User


class ConsoleChannel(DeliveryChannel):
    id = "console"

    def __init__(self) -> None:
        self.delivered: list[tuple[User, MorningBrief]] = []
        self.threads: dict[str, list[str]] = {}

    async def deliver(self, user: User, brief: MorningBrief, channel_cfg: dict) -> DeliveryReceipt:
        self.delivered.append((user, brief))
        return DeliveryReceipt(
            channel=self.id,
            target=user.email,
            delivered_at=datetime.now(UTC),
            external_ref=str(brief.id),
        )

    async def thread_reply(self, thread_ref: str, message: str) -> None:
        self.threads.setdefault(thread_ref, []).append(message)

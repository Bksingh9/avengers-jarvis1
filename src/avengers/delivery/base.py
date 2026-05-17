"""Delivery-channel Protocol (spec §9.4)."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from avengers.schemas.brief import MorningBrief
from avengers.schemas.identity import User


class DeliveryReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel: str
    target: str  # email address, slack user id, etc.
    delivered_at: datetime
    external_ref: str | None = None  # message ts / id from the provider


class DeliveryChannel(Protocol):
    id: str

    async def deliver(self, user: User, brief: MorningBrief, channel_cfg: dict) -> DeliveryReceipt: ...

    async def thread_reply(self, thread_ref: str, message: str) -> None: ...

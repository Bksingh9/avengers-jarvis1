"""Tenant / user / delivery-preference schemas (spec §8.1)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class DeliveryPrefs(BaseModel):
    """Per-user delivery-channel preferences."""

    model_config = ConfigDict(extra="forbid")

    channels: list[str] = Field(default_factory=lambda: ["slack", "email"])
    morning_time_local: str = "07:00"
    quiet_hours_local: tuple[str, str] | None = None
    deep_dive_default_channel: str = "slack"


class Tenant(BaseModel):
    """Top-level tenant record materialized from the tenant YAML."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    region: str
    timezone: str
    locale: str


class User(BaseModel):
    """A user inside a tenant."""

    model_config = ConfigDict(extra="forbid")

    id: str
    tenant_id: str
    email: EmailStr
    display_name: str
    groups: set[str] = Field(default_factory=set)
    timezone: str
    delivery_prefs: DeliveryPrefs = Field(default_factory=DeliveryPrefs)

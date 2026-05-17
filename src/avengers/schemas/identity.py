"""Tenant / user / delivery-preference schemas (spec §8.1).

Note on email validation: Pydantic's `EmailStr` requires the
`email-validator` package, which transitively pulls in `dnspython`
(~30 MB on disk). For deployments where serverless-function size is a
constraint (e.g. Vercel's 250 MB limit), we use a plain `str` with a
small regex validator instead. Identity providers do the real validation
upstream at the IdP boundary anyway.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

# RFC 5322 is a beast; this is the practical subset that covers anything
# any HRIS / IdP will give us, without the dependency footprint of a full
# validator. Identity providers already enforce real-RFC compliance.
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


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
    email: str
    display_name: str
    groups: set[str] = Field(default_factory=set)
    timezone: str
    delivery_prefs: DeliveryPrefs = Field(default_factory=DeliveryPrefs)

    @field_validator("email")
    @classmethod
    def _validate_email(cls, v: str) -> str:
        if not _EMAIL_RE.match(v):
            raise ValueError(f"invalid email: {v!r}")
        return v

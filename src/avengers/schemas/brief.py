"""Brief / digest schemas (spec §8.2).

Every claim that ends up in a brief is wrapped in `Cited`, which requires at
least one `Source`. The `cite_every_claim` policy depends on this invariant.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class Source(BaseModel):
    """A traceable reference back to the tool call that produced a fact."""

    model_config = ConfigDict(extra="forbid")

    connector: str
    tool: str
    ref: str
    ts: datetime


class Cited(BaseModel):
    """A piece of text plus at least one source. Min-length enforced."""

    model_config = ConfigDict(extra="forbid")

    text: str
    sources: list[Source] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)


class Decision(BaseModel):
    """A decision the user should make today, ranked by reversibility."""

    model_config = ConfigDict(extra="forbid")

    text: str
    reversibility: Literal["irreversible", "high_cost", "reversible"]
    deadline: datetime | None = None
    sources: list[Source] = Field(min_length=1)


SectionStatus = Literal["ok", "partial", "skipped", "error"]


class Section(BaseModel):
    """One specialist's contribution to a brief."""

    model_config = ConfigDict(extra="forbid")

    agent: str
    status: SectionStatus
    digest: dict
    latency_ms: int = Field(ge=0)
    cost_usd: float = Field(ge=0)
    error: str | None = None


class MeetingDigest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    yesterday_outcomes: list[Cited] = Field(default_factory=list)
    today_prep: list[Cited] = Field(default_factory=list)
    action_items: list[Cited] = Field(default_factory=list)


class MarketDigest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    watchlist_deltas: list[Cited] = Field(default_factory=list)
    macro_signal: list[Cited] = Field(default_factory=list)
    new_filings: list[Cited] = Field(default_factory=list)


class SecurityDigest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    open_criticals: list[Cited] = Field(default_factory=list)
    anomalies: list[Cited] = Field(default_factory=list)
    needs_approval: list[Cited] = Field(default_factory=list)


class ResearchDigest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic_deltas: list[Cited] = Field(default_factory=list)
    deep_dive: list[Cited] = Field(default_factory=list)


class ContentDigest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    drafts: list[Cited] = Field(default_factory=list)
    publish_candidates: list[Cited] = Field(default_factory=list)


class OpsDigest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kpi_deltas: list[Cited] = Field(default_factory=list)
    queue_health: list[Cited] = Field(default_factory=list)
    on_call: list[Cited] = Field(default_factory=list)


# Fynd-specific digests (BRD §9.1 / §9.2) — shape mirrors the six reference
# specialists above so the Director and dashboard treat them uniformly.


class CatalogDigest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    flagged_listings: list[Cited] = Field(default_factory=list)
    missing_attributes: list[Cited] = Field(default_factory=list)
    pricing_violations: list[Cited] = Field(default_factory=list)


class InventoryDigest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stockout_risks: list[Cited] = Field(default_factory=list)
    slow_movers: list[Cited] = Field(default_factory=list)
    transfer_recommendations: list[Cited] = Field(default_factory=list)


class ReconciliationDigest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    settlement_mismatches: list[Cited] = Field(default_factory=list)
    gst_anomalies: list[Cited] = Field(default_factory=list)
    returns_liability: list[Cited] = Field(default_factory=list)


class MorningBrief(BaseModel):
    """The aggregated daily brief for one user on one date."""

    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    tenant_id: str
    user_id: str
    for_date: date
    decisions_today: list[Decision] = Field(default_factory=list)
    sections: list[Section] = Field(default_factory=list)
    kill_switched: list[str] = Field(default_factory=list)
    generated_at: datetime
    model_versions: dict[str, str] = Field(default_factory=dict)
    total_cost_usd: float = Field(ge=0)


class DeepDiveResult(BaseModel):
    """Output of an on-demand deep-dive (spec §11.2)."""

    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    tenant_id: str
    user_id: str
    query: str
    answer: list[Cited]
    follow_ups: list[str] = Field(default_factory=list)
    generated_at: datetime
    total_cost_usd: float = Field(ge=0)

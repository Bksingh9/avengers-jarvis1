from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from avengers.schemas.brief import Cited, Decision, MorningBrief, Section, Source


def _src() -> Source:
    return Source(connector="gcal", tool="list_events", ref="evt1", ts=datetime.now(UTC))


def test_cited_requires_source():
    with pytest.raises(ValidationError):
        Cited(text="claim", sources=[])


def test_cited_accepts_one_source():
    c = Cited(text="claim", sources=[_src()])
    assert c.confidence == 0.8
    assert len(c.sources) == 1


def test_morning_brief_minimal():
    mb = MorningBrief(
        tenant_id="acme",
        user_id="u1",
        for_date=date(2026, 5, 17),
        generated_at=datetime.now(UTC),
        total_cost_usd=0.0,
    )
    assert mb.kill_switched == []
    assert mb.id is not None


def test_decision_requires_source():
    with pytest.raises(ValidationError):
        Decision(text="ship it", reversibility="irreversible", sources=[])


def test_section_status_constrained():
    sec = Section(agent="meetings", status="ok", digest={}, latency_ms=10, cost_usd=0.0)
    assert sec.status == "ok"
    with pytest.raises(ValidationError):
        Section(agent="x", status="invalid", digest={}, latency_ms=1, cost_usd=0)  # type: ignore[arg-type]

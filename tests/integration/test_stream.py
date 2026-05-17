"""SSE stream — verify start / section* / done frames arrive in order."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from avengers.api.app import create_app
from avengers.api.bootstrap import build_container
from avengers.connectors.base import ConnectorRegistry
from avengers.connectors.fake_connector import FakeConnector
from avengers.identity.static_provider import StaticIdentityProvider
from avengers.llm.base import LLMRegistry
from avengers.llm.fake_provider import FakeLLMProvider
from avengers.schemas.identity import DeliveryPrefs, User
from avengers.schemas.llm import Completion, ToolSchema


def _users():
    return [
        User(
            id="alice",
            tenant_id="acme",
            email="alice@acme.com",
            display_name="Alice",
            groups={"avengers-admin"},
            timezone="Asia/Kolkata",
            delivery_prefs=DeliveryPrefs(channels=["console"]),
        ),
    ]


def _parse_sse(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for frame in text.strip().split("\n\n"):
        event = "message"
        data_lines: list[str] = []
        for line in frame.split("\n"):
            if line.startswith("event:"):
                event = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:") :].strip())
        if data_lines:
            out.append((event, "\n".join(data_lines)))
    return out


@pytest.mark.asyncio
async def test_stream_emits_start_sections_done(tmp_path: Path):
    config_dir = Path(__file__).resolve().parents[2] / "config"
    fake = FakeLLMProvider()
    reg = LLMRegistry()
    reg.register("anthropic", lambda: fake)
    reg.register("fake", lambda: fake)
    connectors = ConnectorRegistry()
    for cid in ("gcal", "polygon", "splunk", "crowdstrike", "github_security",
                "exa_search", "cms", "internal_rag", "snowflake", "pagerduty",
                "jira", "datadog", "sec_edgar"):
        connectors.register(FakeConnector(cid, [ToolSchema(name="x", description="", parameters={})]))

    container = build_container(
        config_dir=config_dir,
        identity=StaticIdentityProvider(_users()),
        llm_registry=reg,
        connectors=connectors,
        memory_root=tmp_path / "mem",
    )

    src = '[{"text":"x","sources":[{"connector":"c","tool":"t","ref":"r","ts":"2026-05-17T00:00:00+00:00"}]}]'
    digests = {
        "meetings":   f'{{"yesterday_outcomes":{src},"today_prep":[],"action_items":[]}}',
        "markets":    f'{{"watchlist_deltas":{src},"macro_signal":[],"new_filings":[]}}',
        "security":   f'{{"open_criticals":[],"anomalies":{src},"needs_approval":[]}}',
        "research":   f'{{"topic_deltas":{src},"deep_dive":[]}}',
        "content":    f'{{"drafts":[],"publish_candidates":{src}}}',
        "operations": f'{{"kpi_deltas":{src},"queue_health":[],"on_call":[]}}',
    }
    # Six specialists, order is non-deterministic — enqueue extras so any
    # ordering of calls finds a response. Each completion is end_turn so the
    # agent finishes after one turn.
    for _ in range(20):
        for body in digests.values():
            fake.enqueue(
                Completion(
                    model="m1",
                    output_text=body,
                    stop_reason="end_turn",
                    input_tokens=10,
                    output_tokens=10,
                    cost_usd=0.001,
                )
            )

    app = create_app(container)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as ac:
        r = await ac.post(
            "/tenants/acme/briefs/stream",
            headers={"Authorization": "Bearer user:alice"},
            json={"for_date": "2026-05-17"},
        )
        assert r.status_code == 200
        events = _parse_sse(r.text)

    kinds = [e for e, _ in events]
    assert kinds[0] == "start"
    assert kinds[-1] == "done"
    # We expect one section per enabled agent in the tenant config (6).
    section_count = kinds.count("section")
    assert section_count == 6, kinds

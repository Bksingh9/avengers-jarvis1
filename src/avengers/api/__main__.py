"""Entry point used by `uvicorn avengers.api.__main__:app` in the Dockerfile.

For local dev with the seeded ACME tenant + a stub identity provider:

  uvicorn avengers.api.__main__:app --reload --port 8080

For production wiring, replace `build_container` here with bindings that point
at real Bedrock + Postgres + S3 + OIDC.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from avengers.api.app import create_app
from avengers.api.bootstrap import build_container
from avengers.connectors.base import ConnectorRegistry
from avengers.connectors.fake_connector import FakeConnector
from avengers.core.tenant import TenantContext
from avengers.identity.static_provider import StaticIdentityProvider
from avengers.llm.base import Capability, LLMProvider, LLMRegistry
from avengers.schemas.identity import DeliveryPrefs, User
from avengers.schemas.llm import Completion, CompletionChunk, Message, ToolSchema

_REPO = Path(__file__).resolve().parents[3]


def _seed_users() -> list[User]:
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
        User(
            id="bob",
            tenant_id="acme",
            email="bob@acme.com",
            display_name="Bob",
            timezone="Asia/Kolkata",
        ),
    ]


_SEED_CLAIM = (
    '{"text":"Demo claim — replace with a real LLM provider.",'
    '"sources":[{"connector":"demo","tool":"seed","ref":"seed",'
    '"ts":"2026-05-17T00:00:00+00:00"}],"confidence":0.5}'
)

# Map the agent's `output_schema` name (which BaseAgent puts in the system
# prompt) to a digest body that matches that schema.
_DEMO_DIGESTS: dict[str, str] = {
    "MeetingDigest":  f'{{"yesterday_outcomes":[{_SEED_CLAIM}],"today_prep":[],"action_items":[]}}',
    "MarketDigest":   f'{{"watchlist_deltas":[{_SEED_CLAIM}],"macro_signal":[],"new_filings":[]}}',
    "SecurityDigest": f'{{"open_criticals":[],"anomalies":[{_SEED_CLAIM}],"needs_approval":[]}}',
    "ResearchDigest": f'{{"topic_deltas":[{_SEED_CLAIM}],"deep_dive":[]}}',
    "ContentDigest":  f'{{"drafts":[],"publish_candidates":[{_SEED_CLAIM}]}}',
    "OpsDigest":      f'{{"kpi_deltas":[{_SEED_CLAIM}],"queue_health":[],"on_call":[]}}',
}


class DemoLLMProvider(LLMProvider):
    """Inspects the system prompt to identify the requesting agent and returns
    a digest body that satisfies that agent's output_schema. Used only by the
    seeded `__main__` so the dashboard renders without a real model key."""

    name = "demo"

    def supports(self, capability: Capability) -> bool:
        return capability in {"tools", "json_schema", "streaming"}

    def estimate_cost_usd(self, in_tokens: int, out_tokens: int, model: str) -> float:
        return 0.0

    async def complete(
        self,
        *,
        model: str,
        messages: list[Message],
        tools: list[ToolSchema] | None = None,
        response_schema: type[BaseModel] | None = None,
        max_tokens: int,
        temperature: float = 0.2,
        timeout_s: float = 30.0,
        tenant_ctx: TenantContext,
        extra: dict[str, Any] | None = None,
    ) -> Completion:
        body = self._pick_body(messages)
        return Completion(
            model=model,
            output_text=body,
            stop_reason="end_turn",
            input_tokens=50,
            output_tokens=30,
            cost_usd=0.0008,
        )

    async def stream(self, **kwargs) -> AsyncIterator[CompletionChunk]:  # type: ignore[no-untyped-def]
        completion = await self.complete(**kwargs)

        async def _gen() -> AsyncIterator[CompletionChunk]:
            yield CompletionChunk(delta_text=completion.output_text)
            yield CompletionChunk(stop_reason=completion.stop_reason)

        return _gen()

    @staticmethod
    def _pick_body(messages: list[Message]) -> str:
        system = next((m.content for m in messages if m.role == "system" and m.content), "")
        for schema_name, body in _DEMO_DIGESTS.items():
            if schema_name in (system or ""):
                return body
        return "{}"  # safe default — every digest accepts empty


def _build():  # type: ignore[no-untyped-def]
    demo_llm = DemoLLMProvider()
    reg = LLMRegistry()
    reg.register("anthropic", lambda: demo_llm)
    reg.register("fake", lambda: demo_llm)
    reg.register("demo", lambda: demo_llm)

    connectors = ConnectorRegistry()
    connectors.register(
        FakeConnector(
            "exa_search",
            [ToolSchema(name="search", description="web search", parameters={"type": "object"})],
        )
    )

    return build_container(
        config_dir=_REPO / "config",
        identity=StaticIdentityProvider(_seed_users()),
        llm_registry=reg,
        connectors=connectors,
        memory_root=_REPO / ".memory",
    )


app = create_app(_build())

"""Entry point used by `uvicorn avengers.api.__main__:app` in the Dockerfile.

For local dev with the seeded ACME tenant + a stub identity provider:

  uvicorn avengers.api.__main__:app --reload --port 8080

For production wiring, replace `build_container` here with bindings that point
at real Bedrock + Postgres + S3 + OIDC.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from avengers.api.app import create_app
from avengers.api.bootstrap import build_container
from avengers.connectors.base import ConnectorRegistry
from avengers.connectors.boltic import BolticConnector
from avengers.connectors.catalog_api import CatalogAPIConnector
from avengers.connectors.fake_connector import FakeConnector
from avengers.connectors.fynd_oms import FyndOMSConnector
from avengers.connectors.jiocommerce import JioCommerceConnector
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
        # Fynd-internal tenant (BRD §9.1) — admin + group-gated for RBAC.
        User(
            id="fynd-alice",
            tenant_id="fynd_internal",
            email="alice@fynd.com",
            display_name="Alice (Fynd)",
            groups={"avengers-admin", "fynd-internal"},
            timezone="Asia/Kolkata",
            delivery_prefs=DeliveryPrefs(channels=["console"]),
        ),
        # User in the Fynd tenant *without* the fynd-internal group — used to
        # demonstrate the RBAC gate on Fynd-only connectors.
        User(
            id="fynd-guest",
            tenant_id="fynd_internal",
            email="guest@fynd.com",
            display_name="Guest (Fynd)",
            groups=set(),
            timezone="Asia/Kolkata",
        ),
        # JARVIS tenant — Cap Brij (the one user this tenant exists for).
        User(
            id="cap-brij",
            tenant_id="jarvis",
            email="cap.brij@example.com",
            display_name="Cap Brij",
            groups={"avengers-admin", "fynd-internal", "jarvis-owner"},
            timezone="Asia/Kolkata",
            delivery_prefs=DeliveryPrefs(channels=["console", "telegram"]),
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
    # Fynd-specific (BRD §9.2)
    "CatalogDigest":        f'{{"flagged_listings":[{_SEED_CLAIM}],"missing_attributes":[],"pricing_violations":[]}}',
    "InventoryDigest":      f'{{"stockout_risks":[{_SEED_CLAIM}],"slow_movers":[],"transfer_recommendations":[]}}',
    "ReconciliationDigest": f'{{"settlement_mismatches":[{_SEED_CLAIM}],"gst_anomalies":[],"returns_liability":[]}}',
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


class _OpenAIAsAnthropic:
    """Shim that lets agent YAMLs keep referring to `anthropic:claude-sonnet-4-6`
    while traffic actually goes to OpenAI.

    The agent YAMLs were written when Anthropic was the default. Rewriting every
    YAML when the operator picks a different provider is busywork; instead we
    substitute the model at the call boundary. Model mapping:

        claude-opus-4-7        → gpt-4o          (premium)
        claude-sonnet-4-6      → gpt-4o-mini     (workhorse, cheaper)
        claude-haiku-4-5       → gpt-4o-mini     (fast)
        anything else          → gpt-4o-mini     (safe default)

    All other behaviour is delegated to the underlying OpenAIProvider, so
    capabilities (tools, json_schema, streaming) are preserved.
    """

    name = "openai-as-anthropic"

    _MODEL_MAP = {
        "claude-opus-4-7":   os.environ.get("OPENAI_MODEL_PREMIUM", "gpt-4o"),
        "claude-sonnet-4-6": os.environ.get("OPENAI_MODEL_DEFAULT", "gpt-4o-mini"),
        "claude-haiku-4-5":  os.environ.get("OPENAI_MODEL_FAST",    "gpt-4o-mini"),
    }
    _FALLBACK = os.environ.get("OPENAI_MODEL_DEFAULT", "gpt-4o-mini")

    def __init__(self, underlying):  # type: ignore[no-untyped-def]
        self._u = underlying

    def supports(self, capability):  # type: ignore[no-untyped-def]
        return self._u.supports(capability)

    def estimate_cost_usd(self, in_tokens, out_tokens, model):  # type: ignore[no-untyped-def]
        return self._u.estimate_cost_usd(in_tokens, out_tokens, self._remap(model))

    async def complete(self, *, model, **kwargs):  # type: ignore[no-untyped-def]
        return await self._u.complete(model=self._remap(model), **kwargs)

    async def stream(self, *, model, **kwargs):  # type: ignore[no-untyped-def]
        return await self._u.stream(model=self._remap(model), **kwargs)

    def _remap(self, model: str) -> str:
        for k, v in self._MODEL_MAP.items():
            if model.startswith(k):
                return v
        return self._FALLBACK


def _build():  # type: ignore[no-untyped-def]
    """Compose the live container.

    Provider selection:
      * If OPENAI_API_KEY is set       → real OpenAI provider (gpt-4o-mini default)
      * If ANTHROPIC_API_KEY is set    → real Anthropic provider (sonnet default)
      * Otherwise                       → DemoLLMProvider (shaped stub for $0 demo)

    The key is read from the environment ONLY — never from any file. Set it
    in Render's Environment Variables UI (encrypted at rest); never commit it.
    """
    reg = LLMRegistry()
    demo_llm = DemoLLMProvider()

    has_openai    = bool(os.environ.get("OPENAI_API_KEY"))
    has_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY"))

    if has_openai:
        from avengers.llm.openai_provider import OpenAIProvider
        openai_provider = OpenAIProvider()
        # Register `openai` AND alias under `anthropic` so the agent YAMLs
        # (which reference `anthropic:claude-sonnet-4-6`) get routed to OpenAI.
        # The model name in the YAML is the SECOND half of the spec — we
        # override it below by registering a thin shim that ignores the
        # requested model and uses an OpenAI one instead.
        reg.register("openai", lambda: openai_provider)
        reg.register("anthropic", lambda: _OpenAIAsAnthropic(openai_provider))
        reg.register("demo", lambda: demo_llm)  # keep demo available for fallback
        reg.register("fake", lambda: demo_llm)
        print("[__main__] OpenAI provider active (OPENAI_API_KEY set)")
    elif has_anthropic:
        from avengers.llm.anthropic_provider import AnthropicProvider
        anth = AnthropicProvider()
        reg.register("anthropic", lambda: anth)
        reg.register("demo", lambda: demo_llm)
        reg.register("fake", lambda: demo_llm)
        print("[__main__] Anthropic provider active (ANTHROPIC_API_KEY set)")
    else:
        # Demo fallback — shaped digests, $0 cost. The dashboard renders,
        # but every reply is a "Demo claim — replace with a real LLM" stub.
        reg.register("anthropic", lambda: demo_llm)
        reg.register("fake", lambda: demo_llm)
        reg.register("demo", lambda: demo_llm)
        print("[__main__] No LLM key set — using DemoLLMProvider stub")

    connectors = ConnectorRegistry()
    connectors.register(
        FakeConnector(
            "exa_search",
            [ToolSchema(name="search", description="web search", parameters={"type": "object"})],
        )
    )
    # Fynd / Jio commerce backends — swappable via env so the same agents and
    # prompts work against either. Set COMMERCE_BACKEND=jio to use only Jio,
    # =fynd for only Fynd (default), =both to register both side-by-side.
    backend = os.getenv("COMMERCE_BACKEND", "fynd").lower()
    if backend in ("fynd", "both"):
        connectors.register(FyndOMSConnector())
    if backend in ("jio", "both"):
        connectors.register(JioCommerceConnector())
    connectors.register(BolticConnector())
    connectors.register(CatalogAPIConnector())

    return build_container(
        config_dir=_REPO / "config",
        identity=StaticIdentityProvider(_seed_users()),
        llm_registry=reg,
        connectors=connectors,
        memory_root=_REPO / ".memory",
        personas_root=_REPO / "memory",  # memory/<tenant>/persona.md
    )


app = create_app(_build())

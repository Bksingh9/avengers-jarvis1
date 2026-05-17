"""Tenant-aware router on top of the LLM registry.

Agents call the router with a *logical* model spec like
`bedrock:claude-sonnet-4-6`. The router splits that into (provider, model),
resolves the provider via the registry, applies retries + cost accounting +
audit, then delegates.
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from avengers.core.tenant import TenantContext
from avengers.llm.base import LLMProvider, LLMProviderError, LLMRegistry, get_registry
from avengers.observability.langfuse_sink import LLMTrace, get_sink
from avengers.observability.metrics import get_metrics
from avengers.observability.tracing import get_tracer
from avengers.schemas.llm import Completion, CompletionChunk, Message, ToolSchema

logger = logging.getLogger(__name__)


def parse_model_spec(spec: str) -> tuple[str, str]:
    """Split `provider:model` (e.g. `bedrock:claude-sonnet-4-6`)."""
    if ":" not in spec:
        raise ValueError(f"model spec must be 'provider:model', got: {spec!r}")
    provider, _, model = spec.partition(":")
    if not provider or not model:
        raise ValueError(f"invalid model spec: {spec!r}")
    return provider, model


class LLMRouter:
    """Routes to providers, handles fallback, and aggregates cost."""

    def __init__(self, registry: LLMRegistry | None = None) -> None:
        self._registry = registry or get_registry()

    async def complete(
        self,
        *,
        spec: str,
        messages: list[Message],
        tools: list[ToolSchema] | None = None,
        response_schema: type[BaseModel] | None = None,
        max_tokens: int,
        temperature: float = 0.2,
        timeout_s: float = 30.0,
        tenant_ctx: TenantContext,
        fallback_spec: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> Completion:
        try:
            return await self._call(
                spec=spec,
                messages=messages,
                tools=tools,
                response_schema=response_schema,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout_s=timeout_s,
                tenant_ctx=tenant_ctx,
                extra=extra,
            )
        except LLMProviderError as exc:
            if not exc.retryable or fallback_spec is None:
                raise
            logger.warning(
                "llm_fallback primary=%s fallback=%s reason=%s",
                spec,
                fallback_spec,
                exc,
            )
            return await self._call(
                spec=fallback_spec,
                messages=messages,
                tools=tools,
                response_schema=response_schema,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout_s=timeout_s,
                tenant_ctx=tenant_ctx,
                extra=extra,
            )

    async def stream(
        self,
        *,
        spec: str,
        messages: list[Message],
        tools: list[ToolSchema] | None = None,
        max_tokens: int,
        temperature: float = 0.2,
        timeout_s: float = 30.0,
        tenant_ctx: TenantContext,
        extra: dict[str, Any] | None = None,
    ) -> AsyncIterator[CompletionChunk]:
        provider_name, model = parse_model_spec(spec)
        provider = await self._registry.get(provider_name)
        if not provider.supports("streaming"):
            raise LLMProviderError(provider_name, "streaming not supported")
        return await provider.stream(
            model=model,
            messages=messages,
            tools=tools,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout_s=timeout_s,
            tenant_ctx=tenant_ctx,
            extra=extra,
        )

    async def _call(
        self,
        *,
        spec: str,
        messages: list[Message],
        tools: list[ToolSchema] | None,
        response_schema: type[BaseModel] | None,
        max_tokens: int,
        temperature: float,
        timeout_s: float,
        tenant_ctx: TenantContext,
        extra: dict[str, Any] | None,
    ) -> Completion:
        provider_name, model = parse_model_spec(spec)
        provider: LLMProvider = await self._registry.get(provider_name)

        if response_schema is not None and not provider.supports("json_schema"):
            raise LLMProviderError(provider_name, "json_schema not supported")
        if tools and not provider.supports("tools"):
            raise LLMProviderError(provider_name, "tools not supported")

        metrics = get_metrics()
        tracer = get_tracer()
        labels = {"provider": provider_name, "model": model, "tenant": tenant_ctx.tenant_id}
        t0 = time.monotonic()
        with tracer.span("llm.call", attrs=labels):
            completion = await provider.complete(
                model=model,
                messages=messages,
                tools=tools,
                response_schema=response_schema,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout_s=timeout_s,
                tenant_ctx=tenant_ctx,
                extra=extra,
            )
        latency_ms = int((time.monotonic() - t0) * 1000)
        metrics.incr("llm.calls", labels=labels)
        metrics.incr("llm.input_tokens", value=completion.input_tokens, labels=labels)
        metrics.incr("llm.output_tokens", value=completion.output_tokens, labels=labels)
        metrics.incr("llm.cost_usd", value=completion.cost_usd, labels=labels)
        metrics.observe("llm.latency_ms", latency_ms, labels=labels)
        try:
            await get_sink().record(
                LLMTrace(
                    tenant_id=tenant_ctx.tenant_id,
                    user_id=tenant_ctx.user_id,
                    agent=(extra or {}).get("agent"),
                    provider=provider_name,
                    model=model,
                    input_tokens=completion.input_tokens,
                    output_tokens=completion.output_tokens,
                    cost_usd=completion.cost_usd,
                    latency_ms=latency_ms,
                    stop_reason=completion.stop_reason,
                    ts=datetime.now(UTC),
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("trace_sink_failed err=%s", exc)
        logger.info(
            "llm_call tenant=%s provider=%s model=%s in=%d out=%d cost_usd=%.4f latency_ms=%d",
            tenant_ctx.tenant_id,
            provider_name,
            model,
            completion.input_tokens,
            completion.output_tokens,
            completion.cost_usd,
            latency_ms,
        )
        return completion

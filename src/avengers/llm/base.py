"""Vendor-agnostic LLM provider Protocol (spec §9.1).

Implementations live in sibling modules. Adapters MUST:
  * translate provider-specific message/tool/result types into the schemas in
    `avengers.schemas.llm` and back,
  * never let a provider exception leak — wrap in `LLMProviderError`,
  * emit an audit event for every call (handled centrally by the router).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Literal, Protocol

from pydantic import BaseModel

from avengers.core.tenant import TenantContext
from avengers.schemas.llm import Completion, CompletionChunk, Message, ToolSchema

Capability = Literal["tools", "json_schema", "vision", "caching", "streaming", "thinking"]


class LLMProviderError(RuntimeError):
    """Wraps any vendor SDK exception so callers never see vendor types."""

    def __init__(self, provider: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(f"{provider}: {message}")
        self.provider = provider
        self.retryable = retryable


class LLMProvider(Protocol):
    """The single interface every model adapter implements."""

    name: str

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
    ) -> Completion: ...

    async def stream(
        self,
        *,
        model: str,
        messages: list[Message],
        tools: list[ToolSchema] | None = None,
        max_tokens: int,
        temperature: float = 0.2,
        timeout_s: float = 30.0,
        tenant_ctx: TenantContext,
        extra: dict[str, Any] | None = None,
    ) -> AsyncIterator[CompletionChunk]: ...

    def supports(self, capability: Capability) -> bool: ...

    def estimate_cost_usd(self, in_tokens: int, out_tokens: int, model: str) -> float: ...


# ---------------------------------------------------------------------------
# Registry: maps provider name -> factory. Tenants/agents reference providers
# by string ("bedrock", "anthropic", ...) so config can be edited without
# changing code.
# ---------------------------------------------------------------------------

ProviderFactory = Callable[[], LLMProvider] | Callable[[], Awaitable[LLMProvider]]


class LLMRegistry:
    """Process-wide registry of provider factories."""

    def __init__(self) -> None:
        self._factories: dict[str, ProviderFactory] = {}
        self._cache: dict[str, LLMProvider] = {}

    def register(self, name: str, factory: ProviderFactory) -> None:
        if name in self._factories:
            raise ValueError(f"provider already registered: {name}")
        self._factories[name] = factory

    async def get(self, name: str) -> LLMProvider:
        if name in self._cache:
            return self._cache[name]
        if name not in self._factories:
            raise KeyError(f"unknown LLM provider: {name}")
        result = self._factories[name]()
        provider = await result if hasattr(result, "__await__") else result  # type: ignore[misc]
        self._cache[name] = provider  # type: ignore[assignment]
        return provider  # type: ignore[return-value]

    def known(self) -> list[str]:
        return sorted(self._factories)


_registry: LLMRegistry | None = None


def get_registry() -> LLMRegistry:
    global _registry
    if _registry is None:
        _registry = LLMRegistry()
    return _registry

"""In-memory deterministic LLM provider used by unit tests and local dev.

Lets the rest of the platform be exercised end-to-end without any network
calls. Configure it by pushing scripted `Completion` objects with `enqueue()`.
"""

from __future__ import annotations

from collections import deque
from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel

from avengers.core.tenant import TenantContext
from avengers.llm.base import Capability, LLMProvider, LLMProviderError
from avengers.schemas.llm import Completion, CompletionChunk, Message, ToolSchema


class FakeLLMProvider(LLMProvider):
    name = "fake"

    def __init__(self) -> None:
        self._queue: deque[Completion] = deque()
        self.calls: list[dict[str, Any]] = []

    def enqueue(self, completion: Completion) -> None:
        self._queue.append(completion)

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
        self.calls.append(
            {
                "model": model,
                "messages": messages,
                "tools": tools,
                "tenant": tenant_ctx.tenant_id,
            }
        )
        if not self._queue:
            raise LLMProviderError(self.name, "no scripted response enqueued")
        return self._queue.popleft()

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
    ) -> AsyncIterator[CompletionChunk]:
        completion = await self.complete(
            model=model,
            messages=messages,
            tools=tools,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout_s=timeout_s,
            tenant_ctx=tenant_ctx,
        )

        async def _gen() -> AsyncIterator[CompletionChunk]:
            for ch in completion.output_text:
                yield CompletionChunk(delta_text=ch)
            yield CompletionChunk(stop_reason=completion.stop_reason)

        return _gen()

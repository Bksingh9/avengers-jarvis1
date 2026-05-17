"""Anthropic Messages API adapter.

The vendor SDK (`anthropic`) is imported lazily inside the methods so the rest
of the codebase can be loaded and tested without the extra installed.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from avengers.core.tenant import TenantContext
from avengers.llm.base import Capability, LLMProvider, LLMProviderError
from avengers.schemas.llm import Completion, CompletionChunk, Message, ToolCall, ToolSchema

if TYPE_CHECKING:  # only for type hints; never at runtime
    from anthropic import AsyncAnthropic

# Per-1M-token list prices (USD). Update when contract pricing changes.
_PRICING: dict[str, tuple[float, float]] = {
    # model              input    output
    "claude-opus-4-7":        (15.0, 75.0),
    "claude-sonnet-4-6":      (3.0,  15.0),
    "claude-haiku-4-5":       (0.8,  4.0),
}


def _price_for(model: str) -> tuple[float, float]:
    for prefix, price in _PRICING.items():
        if model.startswith(prefix):
            return price
    return (3.0, 15.0)  # conservative default


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, *, api_key: str | None = None, base_url: str | None = None) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._client: AsyncAnthropic | None = None

    def _ensure_client(self) -> "AsyncAnthropic":
        if self._client is None:
            try:
                from anthropic import AsyncAnthropic
            except ImportError as exc:
                raise LLMProviderError(self.name, "anthropic SDK not installed") from exc
            self._client = AsyncAnthropic(api_key=self._api_key, base_url=self._base_url)
        return self._client

    def supports(self, capability: Capability) -> bool:
        return capability in {"tools", "json_schema", "vision", "caching", "streaming", "thinking"}

    def estimate_cost_usd(self, in_tokens: int, out_tokens: int, model: str) -> float:
        in_price, out_price = _price_for(model)
        return (in_tokens / 1_000_000) * in_price + (out_tokens / 1_000_000) * out_price

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
        client = self._ensure_client()
        system_text, anthropic_msgs = _to_anthropic_messages(messages)
        anthropic_tools = _to_anthropic_tools(tools) if tools else None

        try:
            resp = await client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_text or None,
                messages=anthropic_msgs,
                tools=anthropic_tools,
                timeout=timeout_s,
                metadata={"user_id": tenant_ctx.user_id or "system"},
            )
        except Exception as exc:  # noqa: BLE001 — wrap & classify
            retryable = type(exc).__name__ in {"APITimeoutError", "RateLimitError", "InternalServerError"}
            raise LLMProviderError(self.name, str(exc), retryable=retryable) from exc

        output_text, tool_calls = _from_anthropic_content(resp.content)
        in_toks = getattr(resp.usage, "input_tokens", 0)
        out_toks = getattr(resp.usage, "output_tokens", 0)
        return Completion(
            model=model,
            output_text=output_text,
            tool_calls=tool_calls,
            stop_reason=_map_stop_reason(getattr(resp, "stop_reason", "end_turn")),
            input_tokens=in_toks,
            output_tokens=out_toks,
            cost_usd=self.estimate_cost_usd(in_toks, out_toks, model),
        )

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
        client = self._ensure_client()
        system_text, anthropic_msgs = _to_anthropic_messages(messages)
        anthropic_tools = _to_anthropic_tools(tools) if tools else None

        async def _gen() -> AsyncIterator[CompletionChunk]:
            try:
                async with client.messages.stream(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system_text or None,
                    messages=anthropic_msgs,
                    tools=anthropic_tools,
                    timeout=timeout_s,
                ) as stream:
                    async for event in stream:
                        if getattr(event, "type", None) == "content_block_delta":
                            delta = getattr(event, "delta", None)
                            text = getattr(delta, "text", "") if delta else ""
                            if text:
                                yield CompletionChunk(delta_text=text)
            except Exception as exc:  # noqa: BLE001
                raise LLMProviderError(self.name, str(exc), retryable=True) from exc

        return _gen()


# ---------------------------------------------------------------------------
# Translation helpers — keep vendor types isolated here.
# ---------------------------------------------------------------------------


def _to_anthropic_messages(messages: list[Message]) -> tuple[str, list[dict[str, Any]]]:
    system_chunks: list[str] = []
    out: list[dict[str, Any]] = []
    for m in messages:
        if m.role == "system":
            if m.content:
                system_chunks.append(m.content)
            continue
        if m.role == "tool":
            assert m.tool_result is not None, "tool message requires tool_result"
            out.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": m.tool_result.tool_call_id,
                            "content": _stringify(m.tool_result.content),
                            "is_error": m.tool_result.is_error,
                        }
                    ],
                }
            )
            continue
        content_blocks: list[dict[str, Any]] = []
        if m.content:
            content_blocks.append({"type": "text", "text": m.content})
        for tc in m.tool_calls:
            content_blocks.append(
                {"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.arguments}
            )
        out.append({"role": m.role, "content": content_blocks})
    return "\n\n".join(system_chunks), out


def _to_anthropic_tools(tools: list[ToolSchema]) -> list[dict[str, Any]]:
    return [
        {"name": t.name, "description": t.description, "input_schema": t.parameters}
        for t in tools
    ]


def _from_anthropic_content(content: list[Any]) -> tuple[str, list[ToolCall]]:
    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    for block in content:
        btype = getattr(block, "type", None) or (block.get("type") if isinstance(block, dict) else None)
        if btype == "text":
            text_parts.append(getattr(block, "text", None) or block["text"])
        elif btype == "tool_use":
            tool_calls.append(
                ToolCall(
                    id=getattr(block, "id", None) or block["id"],
                    name=getattr(block, "name", None) or block["name"],
                    arguments=getattr(block, "input", None) or block["input"],
                )
            )
    return "".join(text_parts), tool_calls


def _map_stop_reason(reason: str) -> str:
    mapping = {
        "end_turn": "end_turn",
        "tool_use": "tool_use",
        "max_tokens": "max_tokens",
        "stop_sequence": "stop_sequence",
    }
    return mapping.get(reason, "end_turn")


def _stringify(content: Any) -> str:
    if isinstance(content, str):
        return content
    import json

    return json.dumps(content, default=str)

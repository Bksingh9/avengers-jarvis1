"""OpenAI Chat Completions adapter.

Vendor SDK (`openai`) is imported lazily inside methods so the rest of the
codebase loads without it installed. Translates between OpenAI's
chat-completion / tool-use schema and our vendor-agnostic types in
`avengers.schemas.llm`. No vendor type ever leaks above this module.

Supports:
  * Chat completions (`gpt-4.1`, `gpt-4o`, `gpt-4o-mini`, `o4-mini`, etc.)
  * Tool use (function calling)
  * Streaming
  * JSON-schema response format
  * Cost estimation per current OpenAI public pricing
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from avengers.core.tenant import TenantContext
from avengers.llm.base import Capability, LLMProvider, LLMProviderError
from avengers.schemas.llm import Completion, CompletionChunk, Message, ToolCall, ToolSchema

if TYPE_CHECKING:
    from openai import AsyncOpenAI


# Approximate USD list prices per 1M tokens. Update when contract pricing
# changes. Order matters in `_price_for` — first prefix match wins.
_PRICING: dict[str, tuple[float, float]] = {
    # model prefix      input    output
    "gpt-4.1":              (2.5,  10.0),
    "gpt-4o-mini":          (0.15, 0.60),
    "gpt-4o":               (2.5,  10.0),
    "o4-mini":              (1.10, 4.40),
    "o3-mini":              (1.10, 4.40),
    "o1-mini":              (3.0,  12.0),
    "o1":                   (15.0, 60.0),
    "gpt-4-turbo":          (10.0, 30.0),
    "gpt-3.5-turbo":        (0.50, 1.50),
}


def _price_for(model: str) -> tuple[float, float]:
    for prefix, price in _PRICING.items():
        if model.startswith(prefix):
            return price
    # Unknown model — conservative default close to gpt-4o.
    return (2.5, 10.0)


class OpenAIProvider(LLMProvider):
    """Adapter against the OpenAI chat-completions API."""

    name = "openai"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        organization: str | None = None,
    ) -> None:
        # Fall through to the env var if the caller didn't supply one. We
        # never log or echo the key; production callers set it via
        # Render's / AWS Secrets Manager's encrypted env injection.
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self._base_url = base_url
        self._organization = organization or os.environ.get("OPENAI_ORG_ID")
        self._client: AsyncOpenAI | None = None

    def _ensure_client(self) -> "AsyncOpenAI":
        if self._client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError as exc:
                raise LLMProviderError(self.name, "openai SDK not installed") from exc
            if not self._api_key:
                raise LLMProviderError(self.name, "OPENAI_API_KEY env var not set")
            self._client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
                organization=self._organization,
            )
        return self._client

    def supports(self, capability: Capability) -> bool:
        return capability in {"tools", "json_schema", "vision", "streaming"}

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
        oai_messages = _to_openai_messages(messages)
        oai_tools = _to_openai_tools(tools) if tools else None

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": oai_messages,
            "max_completion_tokens": max_tokens,
            "temperature": temperature,
            "timeout": timeout_s,
            "user": tenant_ctx.user_id or "system",
        }
        if oai_tools:
            kwargs["tools"] = oai_tools
            kwargs["tool_choice"] = "auto"
        if response_schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": response_schema.__name__,
                    "schema": response_schema.model_json_schema(),
                    "strict": True,
                },
            }

        try:
            resp = await client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001 — wrap + classify
            retryable = type(exc).__name__ in {
                "APITimeoutError", "RateLimitError", "InternalServerError",
                "APIConnectionError", "APIError",
            }
            raise LLMProviderError(self.name, str(exc), retryable=retryable) from exc

        choice = resp.choices[0]
        output_text, tool_calls = _from_openai_message(choice.message)
        usage = resp.usage
        in_toks  = getattr(usage, "prompt_tokens", 0) if usage else 0
        out_toks = getattr(usage, "completion_tokens", 0) if usage else 0

        return Completion(
            model=model,
            output_text=output_text,
            tool_calls=tool_calls,
            stop_reason=_map_finish_reason(choice.finish_reason),
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
        oai_messages = _to_openai_messages(messages)
        oai_tools = _to_openai_tools(tools) if tools else None

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": oai_messages,
            "max_completion_tokens": max_tokens,
            "temperature": temperature,
            "timeout": timeout_s,
            "stream": True,
            "user": tenant_ctx.user_id or "system",
        }
        if oai_tools:
            kwargs["tools"] = oai_tools
            kwargs["tool_choice"] = "auto"

        async def _gen() -> AsyncIterator[CompletionChunk]:
            try:
                stream = await client.chat.completions.create(**kwargs)
                async for chunk in stream:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if delta is None:
                        continue
                    text = getattr(delta, "content", None) or ""
                    if text:
                        yield CompletionChunk(delta_text=text)
                    finish = chunk.choices[0].finish_reason
                    if finish:
                        yield CompletionChunk(stop_reason=_map_finish_reason(finish))
            except Exception as exc:  # noqa: BLE001
                raise LLMProviderError(self.name, str(exc), retryable=True) from exc

        return _gen()


# ---------------------------------------------------------------------------
# Translation helpers — vendor types isolated to this module only.
# ---------------------------------------------------------------------------


def _to_openai_messages(messages: list[Message]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        if m.role == "system":
            if m.content:
                out.append({"role": "system", "content": m.content})
            continue
        if m.role == "tool":
            assert m.tool_result is not None
            out.append({
                "role": "tool",
                "tool_call_id": m.tool_result.tool_call_id,
                "content": _stringify(m.tool_result.content),
            })
            continue
        # assistant or user
        msg: dict[str, Any] = {"role": m.role}
        if m.content:
            msg["content"] = m.content
        if m.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments),
                    },
                }
                for tc in m.tool_calls
            ]
            # OpenAI requires `content` to be present even when only tool calls
            # are sent — empty string is fine.
            msg.setdefault("content", "")
        out.append(msg)
    return out


def _to_openai_tools(tools: list[ToolSchema]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in tools
    ]


def _from_openai_message(message: Any) -> tuple[str, list[ToolCall]]:
    text = getattr(message, "content", None) or ""
    tool_calls: list[ToolCall] = []
    for tc in (getattr(message, "tool_calls", None) or []):
        fn = getattr(tc, "function", None)
        if fn is None:
            continue
        try:
            args = json.loads(fn.arguments) if fn.arguments else {}
        except json.JSONDecodeError:
            args = {"_raw": fn.arguments}
        tool_calls.append(ToolCall(id=tc.id, name=fn.name, arguments=args))
    return text, tool_calls


def _map_finish_reason(reason: str | None) -> str:
    mapping = {
        "stop":          "end_turn",
        "tool_calls":    "tool_use",
        "length":        "max_tokens",
        "content_filter": "stop_sequence",
        None:            "end_turn",
    }
    return mapping.get(reason, "end_turn")


def _stringify(content: Any) -> str:
    if isinstance(content, str):
        return content
    return json.dumps(content, default=str)

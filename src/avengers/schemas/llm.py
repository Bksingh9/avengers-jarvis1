"""Vendor-agnostic message/tool/completion schemas (spec §9.1).

Adapter modules translate provider types into these and back. Nothing outside
`src/avengers/llm/*` may import a vendor SDK.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

MessageRole = Literal["system", "user", "assistant", "tool"]


class ToolSchema(BaseModel):
    """JSON-schema-ish description of a tool exposed to the model."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema object
    write: bool = False


class ToolCall(BaseModel):
    """Model-emitted tool invocation."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    arguments: dict[str, Any]


class ToolResult(BaseModel):
    """Result of a tool invocation, fed back to the model."""

    model_config = ConfigDict(extra="forbid")

    tool_call_id: str
    content: Any
    is_error: bool = False


class Message(BaseModel):
    """A single chat turn."""

    model_config = ConfigDict(extra="forbid")

    role: MessageRole
    content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_result: ToolResult | None = None
    name: str | None = None


class Completion(BaseModel):
    """A vendor-agnostic completion result."""

    model_config = ConfigDict(extra="forbid")

    model: str
    output_text: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    stop_reason: Literal["end_turn", "tool_use", "max_tokens", "stop_sequence", "error"] = "end_turn"
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    raw: dict[str, Any] | None = None  # kept opaque; for debugging only


class CompletionChunk(BaseModel):
    """One element in a streaming response."""

    model_config = ConfigDict(extra="forbid")

    delta_text: str = ""
    tool_call_delta: ToolCall | None = None
    stop_reason: str | None = None

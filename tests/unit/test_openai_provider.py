"""OpenAI provider translation correctness (no live API calls)."""

from avengers.llm.openai_provider import (
    OpenAIProvider,
    _from_openai_message,
    _map_finish_reason,
    _to_openai_messages,
    _to_openai_tools,
    _price_for,
)
from avengers.schemas.llm import Message, ToolCall, ToolResult, ToolSchema


def test_pricing_lookup():
    """Known model prefixes resolve to the expected prices; unknowns fall back."""
    assert _price_for("gpt-4o-mini") == (0.15, 0.60)
    assert _price_for("gpt-4o-2024-08-06") == (2.5, 10.0)
    assert _price_for("o4-mini-high") == (1.10, 4.40)
    # Unknown — falls through to the conservative default
    assert _price_for("some-future-model") == (2.5, 10.0)


def test_messages_translation_basic():
    msgs = [
        Message(role="system", content="be helpful"),
        Message(role="user", content="hi"),
    ]
    out = _to_openai_messages(msgs)
    assert out == [
        {"role": "system", "content": "be helpful"},
        {"role": "user", "content": "hi"},
    ]


def test_messages_translation_with_tool_call_and_result():
    """A tool call from the assistant followed by a tool result message."""
    msgs = [
        Message(
            role="assistant",
            tool_calls=[ToolCall(id="t1", name="search", arguments={"q": "ai"})],
        ),
        Message(role="tool", tool_result=ToolResult(tool_call_id="t1", content={"hits": 1})),
    ]
    out = _to_openai_messages(msgs)
    assert out[0]["role"] == "assistant"
    assert out[0]["tool_calls"][0]["function"]["name"] == "search"
    assert out[0]["tool_calls"][0]["function"]["arguments"] == '{"q": "ai"}'
    assert out[0]["content"] == ""  # OpenAI requires content present even when only calls
    assert out[1]["role"] == "tool"
    assert out[1]["tool_call_id"] == "t1"
    # tool result content is JSON-stringified
    assert "hits" in out[1]["content"]


def test_tools_translation():
    tools = [
        ToolSchema(
            name="search",
            description="search web",
            parameters={"type": "object", "properties": {"q": {"type": "string"}}},
        )
    ]
    out = _to_openai_tools(tools)
    assert out[0]["type"] == "function"
    assert out[0]["function"]["name"] == "search"
    assert out[0]["function"]["parameters"]["properties"]["q"]["type"] == "string"


def test_finish_reason_mapping():
    assert _map_finish_reason("stop") == "end_turn"
    assert _map_finish_reason("tool_calls") == "tool_use"
    assert _map_finish_reason("length") == "max_tokens"
    assert _map_finish_reason(None) == "end_turn"
    assert _map_finish_reason("anything-else") == "end_turn"


def test_response_message_extraction():
    """The reverse path — OpenAI returns text + tool_calls, we extract both."""
    class _Fn:
        def __init__(self, name, arguments):
            self.name = name
            self.arguments = arguments

    class _TC:
        def __init__(self, id, function):
            self.id = id
            self.function = function

    class _Msg:
        def __init__(self, content, tool_calls):
            self.content = content
            self.tool_calls = tool_calls

    msg = _Msg(
        content="here you go",
        tool_calls=[_TC("call_1", _Fn("search", '{"q":"langchain"}'))],
    )
    text, calls = _from_openai_message(msg)
    assert text == "here you go"
    assert len(calls) == 1
    assert calls[0].id == "call_1"
    assert calls[0].name == "search"
    assert calls[0].arguments == {"q": "langchain"}


def test_response_message_malformed_args_kept_as_raw():
    """If OpenAI returns invalid JSON in arguments (shouldn't happen, but…), we
    don't crash — we surface the raw string for diagnosis."""
    class _Fn:
        name = "broken"
        arguments = "{this is not json"

    class _TC:
        id = "c2"
        function = _Fn()

    class _Msg:
        content = ""
        tool_calls = [_TC()]

    text, calls = _from_openai_message(_Msg())
    assert calls[0].arguments == {"_raw": "{this is not json"}


def test_provider_supports_expected_capabilities():
    p = OpenAIProvider(api_key="test-key-not-real")
    assert p.supports("tools")
    assert p.supports("json_schema")
    assert p.supports("vision")
    assert p.supports("streaming")
    assert not p.supports("caching")  # OpenAI prompt-caching is implicit, not configured
    assert not p.supports("thinking")  # we don't expose o1's reasoning_effort yet


def test_estimate_cost_uses_pricing_table():
    p = OpenAIProvider(api_key="test-key-not-real")
    # 1M input + 1M output on gpt-4o-mini = $0.15 + $0.60 = $0.75
    assert abs(p.estimate_cost_usd(1_000_000, 1_000_000, "gpt-4o-mini") - 0.75) < 1e-9

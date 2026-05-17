"""Per-LLM-call trace records (Langfuse-shaped).

Each call is captured as an `LLMTrace`. The default sink is a no-op; tests use
`NullLLMTraceSink.recorded` to inspect. Production binds `LangfuseSink` which
ships traces to the Langfuse SDK (lazy import).
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class LLMTrace(BaseModel):
    """One LLM call's worth of metadata."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    user_id: str | None
    agent: str | None
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int
    stop_reason: str
    ts: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class LLMTraceSink(Protocol):
    async def record(self, trace: LLMTrace) -> None: ...


class NullLLMTraceSink(LLMTraceSink):
    """No-op default. Keeps a small ring buffer for test introspection."""

    _RING_LEN = 256

    def __init__(self) -> None:
        self.recorded: deque[LLMTrace] = deque(maxlen=self._RING_LEN)

    async def record(self, trace: LLMTrace) -> None:
        self.recorded.append(trace)


class LangfuseSink(LLMTraceSink):
    """Lazy-imported Langfuse client. Failure to ship a trace is logged but
    never raised — observability must not break a brief."""

    def __init__(self, *, public_key: str, secret_key: str, host: str | None = None) -> None:
        try:
            from langfuse import Langfuse  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("langfuse SDK not installed") from exc
        self._client = Langfuse(public_key=public_key, secret_key=secret_key, host=host)

    async def record(self, trace: LLMTrace) -> None:
        try:
            self._client.generation(
                name=f"{trace.agent or 'unknown'}::{trace.provider}:{trace.model}",
                input=None,
                output=None,
                model=trace.model,
                metadata={
                    "tenant_id": trace.tenant_id,
                    "user_id": trace.user_id,
                    "agent": trace.agent,
                    "latency_ms": trace.latency_ms,
                    "stop_reason": trace.stop_reason,
                    **trace.metadata,
                },
                usage={
                    "input": trace.input_tokens,
                    "output": trace.output_tokens,
                    "total_cost": trace.cost_usd,
                },
                start_time=trace.ts,
            )
        except Exception as exc:  # noqa: BLE001 — observability never raises
            logger.warning("langfuse_record_failed err=%s", exc)


_current: LLMTraceSink = NullLLMTraceSink()


def get_sink() -> LLMTraceSink:
    return _current


def set_sink(s: LLMTraceSink) -> None:
    global _current
    _current = s


def list_recorded() -> list[LLMTrace]:
    """Test convenience: only meaningful when the active sink keeps a buffer."""
    if isinstance(_current, NullLLMTraceSink):
        return list(_current.recorded)
    return []

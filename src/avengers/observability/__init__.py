"""Observability plane (spec §13).

Three signals:
  * metrics — counters + histograms, Prometheus or in-memory.
  * traces  — spans wrapping LLM calls + tool calls + workflows, OTel-shaped.
  * llm-trace sinks — Langfuse-style per-call records for replay/eval.

All three are no-op by default so importing them adds zero overhead in tests
that don't care about observability.
"""

from avengers.observability.langfuse_sink import (
    LangfuseSink,
    LLMTrace,
    LLMTraceSink,
    NullLLMTraceSink,
    list_recorded,
)
from avengers.observability.metrics import (
    InMemoryMetrics,
    Metrics,
    NullMetrics,
    PrometheusMetrics,
    get_metrics,
    set_metrics,
)
from avengers.observability.tracing import NullTracer, Tracer, get_tracer, set_tracer

__all__ = [
    "InMemoryMetrics",
    "LLMTrace",
    "LLMTraceSink",
    "LangfuseSink",
    "Metrics",
    "NullLLMTraceSink",
    "NullMetrics",
    "NullTracer",
    "PrometheusMetrics",
    "Tracer",
    "get_metrics",
    "get_tracer",
    "list_recorded",
    "set_metrics",
    "set_tracer",
]

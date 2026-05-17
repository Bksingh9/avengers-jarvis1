"""Span tracer surface.

`get_tracer().span(name, attrs)` is a context manager. The default impl is a
no-op so library code can be imported anywhere. Production binds an
OpenTelemetry-backed tracer at startup; see comments below for the wiring.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, Protocol


class Tracer(Protocol):
    @contextmanager
    def span(self, name: str, attrs: dict[str, Any] | None = None) -> Iterator[None]: ...


class NullTracer(Tracer):
    @contextmanager
    def span(self, name: str, attrs: dict[str, Any] | None = None) -> Iterator[None]:
        yield


class RecordingTracer(Tracer):
    """Captures every span open/close for assertions in tests."""

    def __init__(self) -> None:
        self.opened: list[tuple[str, dict[str, Any]]] = []
        self.closed: list[str] = []

    @contextmanager
    def span(self, name: str, attrs: dict[str, Any] | None = None) -> Iterator[None]:
        self.opened.append((name, dict(attrs or {})))
        try:
            yield
        finally:
            self.closed.append(name)


# Real OTel integration lives here when `opentelemetry-sdk` is installed.
# The shape is intentionally simple — most spans we open are wrappers around
# tool calls, model calls, and workflows; richer instrumentation can be added
# inside the adapter modules without touching agent/workflow code.

_current: Tracer = NullTracer()


def get_tracer() -> Tracer:
    return _current


def set_tracer(t: Tracer) -> None:
    global _current
    _current = t

"""Backend-agnostic metrics surface.

Bind `set_metrics(PrometheusMetrics())` once at startup; everything else uses
`get_metrics()`. Defaults to `NullMetrics` so library code is safe to import
without a backend.

Cardinality discipline: callers MUST pass small finite label-value sets.
Never thread untrusted user input straight into a label.
"""

from __future__ import annotations

from collections import defaultdict
from threading import Lock
from typing import Protocol


def _label_key(labels: dict[str, str] | None) -> tuple[tuple[str, str], ...]:
    if not labels:
        return ()
    return tuple(sorted(labels.items()))


class Metrics(Protocol):
    def incr(self, name: str, value: float = 1.0, labels: dict[str, str] | None = None) -> None: ...

    def observe(self, name: str, value: float, labels: dict[str, str] | None = None) -> None: ...


class NullMetrics(Metrics):
    def incr(self, name: str, value: float = 1.0, labels: dict[str, str] | None = None) -> None: ...

    def observe(self, name: str, value: float, labels: dict[str, str] | None = None) -> None: ...


class InMemoryMetrics(Metrics):
    """Thread-safe in-memory backend for tests and local dev."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: dict[str, dict[tuple, float]] = defaultdict(lambda: defaultdict(float))
        self._observations: dict[str, list[tuple[tuple, float]]] = defaultdict(list)

    def incr(self, name: str, value: float = 1.0, labels: dict[str, str] | None = None) -> None:
        with self._lock:
            self._counters[name][_label_key(labels)] += value

    def observe(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        with self._lock:
            self._observations[name].append((_label_key(labels), value))

    # ----- inspection helpers used by tests --------------------------------

    def counter(self, name: str, labels: dict[str, str] | None = None) -> float:
        return self._counters[name].get(_label_key(labels), 0.0)

    def observations(self, name: str, labels: dict[str, str] | None = None) -> list[float]:
        key = _label_key(labels)
        return [v for k, v in self._observations[name] if k == key or labels is None]


class PrometheusMetrics(Metrics):
    """Lazy-imports `prometheus_client`. One Counter/Histogram per metric name."""

    def __init__(self, namespace: str = "avengers") -> None:
        try:
            import prometheus_client  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "prometheus_client not installed; install avengers[observability]"
            ) from exc
        from prometheus_client import REGISTRY

        self._namespace = namespace
        self._registry = REGISTRY
        self._counters: dict[str, object] = {}
        self._histograms: dict[str, object] = {}
        self._lock = Lock()

    def _counter(self, name: str, labels: dict[str, str] | None):  # type: ignore[no-untyped-def]
        from prometheus_client import Counter

        key = name
        with self._lock:
            if key not in self._counters:
                self._counters[key] = Counter(
                    f"{self._namespace}_{name.replace('.', '_')}",
                    f"avengers counter {name}",
                    labelnames=sorted((labels or {}).keys()),
                )
            return self._counters[key]

    def _hist(self, name: str, labels: dict[str, str] | None):  # type: ignore[no-untyped-def]
        from prometheus_client import Histogram

        key = name
        with self._lock:
            if key not in self._histograms:
                self._histograms[key] = Histogram(
                    f"{self._namespace}_{name.replace('.', '_')}",
                    f"avengers histogram {name}",
                    labelnames=sorted((labels or {}).keys()),
                )
            return self._histograms[key]

    def incr(self, name: str, value: float = 1.0, labels: dict[str, str] | None = None) -> None:
        c = self._counter(name, labels)
        if labels:
            c.labels(**labels).inc(value)  # type: ignore[attr-defined]
        else:
            c.inc(value)  # type: ignore[attr-defined]

    def observe(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        h = self._hist(name, labels)
        if labels:
            h.labels(**labels).observe(value)  # type: ignore[attr-defined]
        else:
            h.observe(value)  # type: ignore[attr-defined]


_current: Metrics = NullMetrics()


def get_metrics() -> Metrics:
    return _current


def set_metrics(m: Metrics) -> None:
    global _current
    _current = m

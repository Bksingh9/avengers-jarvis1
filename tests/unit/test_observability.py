from avengers.observability.metrics import InMemoryMetrics, NullMetrics
from avengers.observability.tracing import NullTracer, RecordingTracer


def test_null_metrics_noop():
    m = NullMetrics()
    m.incr("x")
    m.observe("y", 1.0)
    # nothing to assert beyond "no exception"


def test_in_memory_counter_and_histogram():
    m = InMemoryMetrics()
    m.incr("calls", labels={"agent": "research"})
    m.incr("calls", value=2.0, labels={"agent": "research"})
    m.incr("calls", labels={"agent": "markets"})
    m.observe("latency_ms", 100, labels={"agent": "research"})
    m.observe("latency_ms", 250, labels={"agent": "research"})

    assert m.counter("calls", {"agent": "research"}) == 3.0
    assert m.counter("calls", {"agent": "markets"}) == 1.0
    assert m.observations("latency_ms", {"agent": "research"}) == [100, 250]


def test_recording_tracer():
    t = RecordingTracer()
    with t.span("outer", {"k": "v"}):
        with t.span("inner"):
            pass
    assert [n for n, _ in t.opened] == ["outer", "inner"]
    assert t.closed == ["inner", "outer"]
    assert t.opened[0][1] == {"k": "v"}


def test_null_tracer_does_nothing():
    with NullTracer().span("x"):
        pass

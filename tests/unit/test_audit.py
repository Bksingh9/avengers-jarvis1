from avengers.core.audit import Auditor, InMemoryAuditSink


async def test_emits_and_redacts():
    sink = InMemoryAuditSink()
    a = Auditor(sink)
    ev = await a.emit(
        tenant_id="acme",
        actor="agent:research",
        kind="tool.invoke",
        target="exa_search.search",
        payload={"query": "email alice@example.com"},
    )
    assert ev.tenant_id == "acme"
    assert len(sink.events) == 1
    _, redacted = sink.events[0]
    assert "<EMAIL>" in redacted
    assert "alice@example.com" not in redacted


async def test_payload_hash_stable():
    sink = InMemoryAuditSink()
    a = Auditor(sink)
    e1 = await a.emit(tenant_id="t", actor="x", kind="k", target="t", payload={"a": 1, "b": 2})
    e2 = await a.emit(tenant_id="t", actor="x", kind="k", target="t", payload={"b": 2, "a": 1})
    assert e1.payload_hash == e2.payload_hash

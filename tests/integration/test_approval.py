"""Approval queue: enqueue → human decides → coroutine resolves with the verdict."""

from __future__ import annotations

import asyncio

import pytest

from avengers.workflows.approval import (
    ApprovalQueue,
    ApprovalTimeoutError,
    request_approval,
)


async def test_approve_unblocks_waiter():
    q = ApprovalQueue()
    req = await request_approval(
        q,
        tenant_id="acme",
        agent="content",
        user_id="u1",
        action="cms.publish",
        payload={"draft_id": "d1"},
    )
    waiter = asyncio.create_task(q.await_decision(req.id, timeout_s=5))
    await asyncio.sleep(0)  # let waiter park
    decided = await q.decide(req.id, decided_by="u1", decision="approved", reason="lgtm")
    assert decided.status == "approved"
    out = await waiter
    assert out.status == "approved"
    assert out.decided_by == "u1"


async def test_deny_short_circuits():
    q = ApprovalQueue()
    req = await request_approval(
        q, tenant_id="acme", agent="ops", user_id="u1", action="x", payload={}
    )
    await q.decide(req.id, decided_by="u2", decision="denied")
    out = await q.await_decision(req.id, timeout_s=5)
    assert out.status == "denied"


async def test_timeout_marks_expired():
    q = ApprovalQueue()
    req = await request_approval(
        q, tenant_id="acme", agent="ops", user_id="u1", action="x", payload={}
    )
    with pytest.raises(ApprovalTimeoutError):
        await q.await_decision(req.id, timeout_s=0.05)
    pending = await q.list_pending("acme")
    assert pending == []  # moved out of pending into expired


async def test_list_pending_filters_by_tenant():
    q = ApprovalQueue()
    await request_approval(q, tenant_id="a", agent="x", user_id="u", action="x", payload={})
    await request_approval(q, tenant_id="b", agent="x", user_id="u", action="x", payload={})
    assert len(await q.list_pending("a")) == 1
    assert len(await q.list_pending()) == 2

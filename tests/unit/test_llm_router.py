import pytest

from avengers.core.tenant import TenantContext
from avengers.llm.base import LLMRegistry
from avengers.llm.fake_provider import FakeLLMProvider
from avengers.llm.router import LLMRouter, parse_model_spec
from avengers.schemas.audit import AuditEvent  # noqa: F401  (ensures schemas import cleanly)
from avengers.schemas.config import (
    AuditCfg,
    BudgetCfg,
    IdentityCfg,
    LLMRoutingCfg,
    TenantConfig,
)
from avengers.schemas.llm import Completion, Message


def _ctx() -> TenantContext:
    tenant = TenantConfig(
        id="acme",
        name="ACME",
        region="us-east-1",
        identity=IdentityCfg(provider="oidc", issuer="https://x"),
        secrets_namespace="ns",
        kms_key_arn="arn:kms:x",
        audit=AuditCfg(bucket="b"),
        budgets=BudgetCfg(daily_usd_cap=10, per_user_usd_cap=1),
        llm_routing=LLMRoutingCfg(default="fake:m1"),
    )
    return TenantContext(tenant=tenant)


def test_parse_model_spec():
    assert parse_model_spec("bedrock:claude-sonnet-4-6") == ("bedrock", "claude-sonnet-4-6")
    with pytest.raises(ValueError):
        parse_model_spec("nocolon")
    with pytest.raises(ValueError):
        parse_model_spec(":model")


async def test_router_dispatches_to_fake():
    reg = LLMRegistry()
    fake = FakeLLMProvider()
    reg.register("fake", lambda: fake)
    router = LLMRouter(registry=reg)
    fake.enqueue(Completion(model="m1", output_text="hi", input_tokens=10, output_tokens=2))
    out = await router.complete(
        spec="fake:m1",
        messages=[Message(role="user", content="hello")],
        max_tokens=50,
        tenant_ctx=_ctx(),
    )
    assert out.output_text == "hi"
    assert fake.calls and fake.calls[0]["tenant"] == "acme"


async def test_router_streams():
    reg = LLMRegistry()
    fake = FakeLLMProvider()
    reg.register("fake", lambda: fake)
    router = LLMRouter(registry=reg)
    fake.enqueue(Completion(model="m1", output_text="abc", input_tokens=1, output_tokens=3))
    gen = await router.stream(
        spec="fake:m1",
        messages=[Message(role="user", content="x")],
        max_tokens=10,
        tenant_ctx=_ctx(),
    )
    chunks = [c async for c in gen]
    assert "".join(c.delta_text for c in chunks if c.delta_text) == "abc"

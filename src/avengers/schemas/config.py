"""Configuration schemas (spec §7).

Tenants, agents, connectors, and policies are all declarative YAML, validated
at startup and reloaded on SIGHUP.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ---------------------------------------------------------------------------
# Tenant
# ---------------------------------------------------------------------------


class IdentityCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["oidc", "saml"]
    issuer: str
    client_id_ref: str | None = None
    client_secret_ref: str | None = None
    group_claim: str = "groups"


class AuditCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bucket: str
    retention_years: int = Field(default=7, ge=1)
    pii_redaction: Literal["off", "standard", "strict"] = "strict"


class BudgetCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")

    daily_usd_cap: float = Field(gt=0)
    per_user_usd_cap: float = Field(gt=0)
    alert_threshold_pct: int = Field(default=80, ge=1, le=100)


class LLMRoutingCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default: str
    classifiers: str | None = None
    high_volume: str | None = None
    sovereign: str | None = None


class DeliveryCfg(BaseModel):
    model_config = ConfigDict(extra="allow")

    default_channels: list[str] = Field(default_factory=lambda: ["slack", "email"])


class WorkspaceCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    members_group: str
    agent_overrides: dict[str, dict[str, Any]] = Field(default_factory=dict)


class TenantConfig(BaseModel):
    """Materialized form of `config/tenants/<id>.yaml`."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    region: str
    locale: str = "en-US"
    timezone: str = "UTC"
    identity: IdentityCfg
    secrets_namespace: str
    kms_key_arn: str
    audit: AuditCfg
    budgets: BudgetCfg
    llm_routing: LLMRoutingCfg
    delivery: DeliveryCfg = Field(default_factory=DeliveryCfg)
    agents_enabled: list[str] = Field(default_factory=list)
    workspaces: list[WorkspaceCfg] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class ModelCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary: str
    fallback: str | None = None
    max_thinking_tokens: int = Field(default=0, ge=0)
    temperature: float = Field(default=0.2, ge=0, le=2)


class ToolsCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")

    builtin: list[str] = Field(default_factory=list)
    mcp: list[str] = Field(default_factory=list)


class LimitsCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_turns: int = Field(default=12, ge=1)
    max_tokens_in: int = Field(default=200_000, ge=1)
    max_tokens_out: int = Field(default=4_000, ge=1)
    wallclock_seconds: int = Field(default=60, ge=1)


class HilCfg(BaseModel):
    """human-in-the-loop policy."""

    model_config = ConfigDict(extra="forbid")

    required_for: list[str] = Field(default_factory=list)


class ScheduleCfg(BaseModel):
    model_config = ConfigDict(extra="allow")


class EvalCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")

    set: str
    gate_score: float = Field(ge=0, le=1)


class AgentConfig(BaseModel):
    """Materialized form of `config/agents/<id>.yaml`."""

    model_config = ConfigDict(extra="forbid")

    id: str
    display_name: str
    version: str
    description: str = ""
    model: ModelCfg
    prompt: str  # path relative to repo root
    input_schema: str
    output_schema: str
    tools: ToolsCfg = Field(default_factory=ToolsCfg)
    limits: LimitsCfg = Field(default_factory=LimitsCfg)
    policies: list[str] = Field(default_factory=list)
    human_in_the_loop: HilCfg = Field(default_factory=HilCfg)
    schedule: ScheduleCfg | None = None
    evals: EvalCfg | None = None


# ---------------------------------------------------------------------------
# Connector
# ---------------------------------------------------------------------------


class AuthCfg(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str  # "oauth2_client_credentials" | "bearer" | "basic" | ...


class RbacCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required_groups_any: list[str] = Field(default_factory=list)
    required_groups_all: list[str] = Field(default_factory=list)


class ToolSafetyCfg(BaseModel):
    model_config = ConfigDict(extra="allow")


class ConnectorToolCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    write: bool = False
    rate_limit_per_min: int = Field(default=60, ge=1)
    safety: ToolSafetyCfg = Field(default_factory=ToolSafetyCfg)


class CachingCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ttl_seconds: int = Field(default=0, ge=0)
    key_fields: list[str] = Field(default_factory=list)


class ConnectorConfig(BaseModel):
    """Materialized form of `config/connectors/<id>.yaml`."""

    model_config = ConfigDict(extra="forbid")

    id: str
    display_name: str
    mcp_server: str  # python entrypoint, e.g. "avengers.connectors.snowflake:server"
    auth: AuthCfg
    scopes: list[str] = Field(default_factory=list)
    rbac: RbacCfg = Field(default_factory=RbacCfg)
    tools: list[ConnectorToolCfg] = Field(default_factory=list)
    caching: CachingCfg = Field(default_factory=CachingCfg)


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------

Hook = Literal["pre_tool", "post_tool", "pre_deliver"]
PolicyAction = Literal["allow", "deny", "rewrite", "enqueue_approval"]


class PolicyAuditCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: Literal["info", "warn", "high", "critical"] = "info"
    code: str | None = None


class PolicyConfig(BaseModel):
    """Materialized form of a single policy YAML.

    `match` and `condition` are evaluated by the policy engine — kept as plain
    dicts/strings here because the engine has its own mini-DSL.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    description: str = ""
    when: Hook
    match: dict[str, Any] = Field(default_factory=dict)
    condition: str | None = None
    action: PolicyAction
    mutate: str | None = None
    audit: PolicyAuditCfg = Field(default_factory=PolicyAuditCfg)

    @model_validator(mode="after")
    def _check_action_args(self) -> "PolicyConfig":
        if self.action == "rewrite" and self.mutate is None:
            raise ValueError("policy action=rewrite requires `mutate`")
        return self

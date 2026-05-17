"""Policy engine (spec §9.6).

Policies are declarative (YAML, see §7.4). Each policy targets one hook —
`pre_tool`, `post_tool`, or `pre_deliver` — and may `allow`, `deny`,
`rewrite`, or `enqueue_approval`.

`condition` and `mutate` are names of registered functions, not arbitrary
expressions. Keeping it a closed registry instead of `eval()` is the whole
point: a malicious tenant YAML can never execute code.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from avengers.core.redact import contains_pii
from avengers.schemas.brief import Cited
from avengers.schemas.config import PolicyConfig
from avengers.schemas.llm import ToolCall, ToolSchema

logger = logging.getLogger(__name__)

Hook = Literal["pre_tool", "post_tool", "pre_deliver"]


# ---------------------------------------------------------------------------
# Context passed to policies at each hook
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class PolicyContext:
    hook: Hook
    agent: str
    tool_schema: ToolSchema | None = None
    tool_call: ToolCall | None = None
    tool_result: Any = None
    digest: Any = None
    user_id: str | None = None
    has_approval: bool = False
    extras: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Allow:
    pass


@dataclass(slots=True)
class Deny:
    reason: str
    code: str | None = None


@dataclass(slots=True)
class Rewrite:
    new_value: Any
    reason: str


@dataclass(slots=True)
class EnqueueApproval:
    reason: str


PolicyDecision = Allow | Deny | Rewrite | EnqueueApproval


# ---------------------------------------------------------------------------
# Condition + mutator registries
# ---------------------------------------------------------------------------

Condition = Callable[[PolicyContext], bool]
Mutator = Callable[[Any, PolicyContext], Any]


class _Registry:
    def __init__(self) -> None:
        self.conditions: dict[str, Condition] = {}
        self.mutators: dict[str, Mutator] = {}

    def condition(self, name: str) -> Callable[[Condition], Condition]:
        def deco(fn: Condition) -> Condition:
            if name in self.conditions:
                raise ValueError(f"condition already registered: {name}")
            self.conditions[name] = fn
            return fn

        return deco

    def mutator(self, name: str) -> Callable[[Mutator], Mutator]:
        def deco(fn: Mutator) -> Mutator:
            if name in self.mutators:
                raise ValueError(f"mutator already registered: {name}")
            self.mutators[name] = fn
            return fn

        return deco


registry = _Registry()


# ---------------------------------------------------------------------------
# Built-in conditions / mutators
# ---------------------------------------------------------------------------


@registry.condition("contains_pii")
def _cond_contains_pii(ctx: PolicyContext) -> bool:
    if ctx.tool_call is None:
        return False
    for v in ctx.tool_call.arguments.values():
        if isinstance(v, str) and contains_pii(v):
            return True
    return False


@registry.condition("digest_has_unsourced_claims")
def _cond_unsourced_claims(ctx: PolicyContext) -> bool:
    """True if any `Cited` in the digest has zero sources or any free-form
    string field is non-empty and lives next to a Cited list — overlay logic
    handled by `drop_unsourced_claims`. We simply detect Cited objects with
    weak provenance.
    """
    digest = ctx.digest
    if digest is None:
        return False
    for value in _walk(digest):
        if isinstance(value, Cited) and not value.sources:
            return True
    return False


@registry.condition("not_has_approval")
def _cond_no_approval(ctx: PolicyContext) -> bool:
    return not ctx.has_approval


@registry.mutator("drop_unsourced_claims")
def _mut_drop_unsourced(value: Any, ctx: PolicyContext) -> Any:
    """Filter every list[Cited] inside `value`, keeping only items with ≥1 source."""
    return _filter_cited(value)


def _walk(obj: Any):
    if isinstance(obj, Cited):
        yield obj
        return
    if hasattr(obj, "model_dump"):
        for v in obj.model_dump().values():
            yield from _walk(v)
        return
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _walk(v)
        return
    if isinstance(obj, list | tuple):
        for v in obj:
            yield from _walk(v)


def _filter_cited(obj: Any) -> Any:
    if isinstance(obj, list):
        return [_filter_cited(v) for v in obj if not (isinstance(v, Cited) and not v.sources)]
    if hasattr(obj, "model_copy"):
        # walk model fields
        updates: dict[str, Any] = {}
        for name in obj.__class__.model_fields:  # type: ignore[attr-defined]
            cur = getattr(obj, name)
            new = _filter_cited(cur)
            if new is not cur:
                updates[name] = new
        return obj.model_copy(update=updates) if updates else obj
    if isinstance(obj, dict):
        return {k: _filter_cited(v) for k, v in obj.items()}
    return obj


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class PolicyEngine:
    def __init__(self, policies: list[PolicyConfig]) -> None:
        self._by_hook: dict[Hook, list[PolicyConfig]] = {
            "pre_tool": [],
            "post_tool": [],
            "pre_deliver": [],
        }
        for p in policies:
            self._by_hook[p.when].append(p)

    def evaluate(self, hook: Hook, ctx: PolicyContext) -> PolicyDecision:
        for policy in self._by_hook.get(hook, []):
            if not self._matches(policy, ctx):
                continue
            if policy.condition is not None:
                cond = self._resolve_condition(policy.condition)
                if not cond(ctx):
                    continue
            decision = self._apply_action(policy, ctx)
            logger.info(
                "policy_fire id=%s hook=%s action=%s agent=%s",
                policy.id,
                hook,
                policy.action,
                ctx.agent,
            )
            return decision
        return Allow()

    # ----- internals --------------------------------------------------------

    def _matches(self, policy: PolicyConfig, ctx: PolicyContext) -> bool:
        match = policy.match or {}
        # `tool.name in [a, b]` -> {"tool.name": {"in": [...]}} or just a list
        for key, expected in match.items():
            actual = self._extract(key, ctx)
            if isinstance(expected, dict) and "in" in expected:
                if actual not in expected["in"]:
                    return False
            elif isinstance(expected, str) and expected.startswith("in ["):
                allowed = [x.strip() for x in expected[len("in ["):-1].split(",")]
                if actual not in allowed:
                    return False
            elif expected == "any":
                continue
            else:
                if actual != expected:
                    return False
        return True

    def _extract(self, key: str, ctx: PolicyContext) -> Any:
        if key == "tool.name":
            return ctx.tool_call.name if ctx.tool_call else None
        if key == "tool.write":
            return ctx.tool_schema.write if ctx.tool_schema else False
        if key == "agent":
            return ctx.agent
        return ctx.extras.get(key)

    def _resolve_condition(self, name: str) -> Condition:
        normalized = name.replace("not has_approval", "not_has_approval")
        if normalized in registry.conditions:
            return registry.conditions[normalized]
        # `fn(x)` — accept the bare function name; we don't evaluate args.
        bare = normalized.split("(", 1)[0]
        if bare in registry.conditions:
            return registry.conditions[bare]
        raise KeyError(f"unknown policy condition: {name}")

    def _apply_action(self, policy: PolicyConfig, ctx: PolicyContext) -> PolicyDecision:
        if policy.action == "allow":
            return Allow()
        if policy.action == "deny":
            return Deny(reason=policy.description or policy.id, code=policy.audit.code)
        if policy.action == "enqueue_approval":
            return EnqueueApproval(reason=policy.description or policy.id)
        if policy.action == "rewrite":
            assert policy.mutate is not None
            mut = registry.mutators[policy.mutate]
            target = ctx.tool_result if ctx.hook == "post_tool" else ctx.digest
            new_val = mut(target, ctx)
            return Rewrite(new_value=new_val, reason=policy.description or policy.id)
        raise ValueError(f"unknown action: {policy.action}")

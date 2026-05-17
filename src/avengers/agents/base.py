"""Base agent: a bounded tool-use loop with policy + audit + budget hooks.

`run()` executes:
  1. seed the conversation with the agent's system prompt + caller-provided input,
  2. call the LLM (router) with the union of all connector tools,
  3. for each tool-use block in the response:
        - resolve the connector by tool-name prefix,
        - run `pre_tool` policies → deny/approval/allow,
        - invoke the connector,
        - run `post_tool` policies → optionally rewrite the result,
        - emit an audit event,
  4. feed tool results back to the LLM,
  5. stop when the model returns `end_turn`, the max_turns is hit, or
     the agent's wallclock budget elapses.

The final response is parsed into the agent's typed `output_schema`. If parsing
fails, the agent returns `AgentResult(status="error", ...)`.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from avengers.connectors.base import (
    ConnectorClient,
    ConnectorRegistry,
    ToolInvocation,
)
from avengers.core.audit import Auditor
from avengers.core.budget import BudgetExceededError, BudgetTracker
from avengers.core.policy import (
    Allow,
    Deny,
    EnqueueApproval,
    PolicyContext,
    PolicyEngine,
    Rewrite,
)
from avengers.core.tenant import TenantContext
from avengers.llm.router import LLMRouter
from avengers.observability.metrics import get_metrics
from avengers.observability.tracing import get_tracer
from avengers.schemas.config import AgentConfig
from avengers.schemas.llm import Message, ToolCall, ToolResult, ToolSchema

logger = logging.getLogger(__name__)


TOut = TypeVar("TOut", bound=BaseModel)


@dataclass(slots=True)
class AgentDeps:
    """Wiring an agent needs to do its job. Injected by the workflow layer."""

    router: LLMRouter
    connectors: ConnectorRegistry
    policies: PolicyEngine
    auditor: Auditor
    budget: BudgetTracker | None = None
    system_prompts: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class AgentResult(Generic[TOut]):
    """Outcome of a single agent run."""

    status: str  # ok | partial | error
    output: TOut | None
    raw_text: str
    latency_ms: int
    cost_usd: float
    tool_calls: int
    error: str | None = None
    needs_approval: list[ToolCall] = field(default_factory=list)


class BaseAgent(Generic[TOut]):
    """Subclass per specialist; set class-level config + output_schema."""

    output_schema: type[TOut]  # set by subclasses

    def __init__(self, config: AgentConfig, deps: AgentDeps) -> None:
        self.config = config
        self.deps = deps

    # ----- public API ------------------------------------------------------

    async def run(
        self,
        *,
        input_payload: dict[str, Any],
        ctx: TenantContext,
    ) -> AgentResult[TOut]:
        t0 = time.monotonic()
        metrics = get_metrics()
        tracer = get_tracer()
        agent_labels = {"agent": self.config.id, "tenant": ctx.tenant_id}
        metrics.incr("agent.runs", labels=agent_labels)
        tools, tool_index = await self._collect_tools()
        messages: list[Message] = [
            Message(role="system", content=self._system_prompt(ctx=ctx)),
            Message(role="user", content=json.dumps(input_payload, default=str)),
        ]
        total_cost = 0.0
        total_tool_calls = 0
        needs_approval: list[ToolCall] = []
        last_text = ""
        error: str | None = None

        for turn in range(self.config.limits.max_turns):
            if (time.monotonic() - t0) * 1000 > self.config.limits.wallclock_seconds * 1000:
                error = "wallclock_exceeded"
                break
            try:
                completion = await self.deps.router.complete(
                    spec=self.config.model.primary,
                    fallback_spec=self.config.model.fallback,
                    messages=messages,
                    tools=tools or None,
                    max_tokens=self.config.limits.max_tokens_out,
                    temperature=self.config.model.temperature,
                    timeout_s=float(self.config.limits.wallclock_seconds),
                    tenant_ctx=ctx,
                )
            except Exception as exc:  # noqa: BLE001
                error = f"llm:{exc}"
                break

            total_cost += completion.cost_usd
            last_text = completion.output_text or last_text

            # Budget pre-check before next iteration
            if self.deps.budget is not None:
                try:
                    await self.deps.budget.try_charge(
                        tenant_id=ctx.tenant_id,
                        user_id=ctx.user_id,
                        cost_usd=completion.cost_usd,
                        daily_cap=ctx.tenant.budgets.daily_usd_cap,
                        per_user_cap=ctx.tenant.budgets.per_user_usd_cap,
                    )
                except BudgetExceededError as exc:
                    error = str(exc)
                    break

            if not completion.tool_calls:
                break  # model produced final answer

            # Add assistant message carrying the tool calls
            messages.append(
                Message(role="assistant", content=completion.output_text, tool_calls=completion.tool_calls)
            )

            # Execute each tool call
            tool_results: list[Message] = []
            for tc in completion.tool_calls:
                total_tool_calls += 1
                schema = tool_index.get(tc.name)
                if schema is None:
                    tool_results.append(
                        Message(
                            role="tool",
                            tool_result=ToolResult(
                                tool_call_id=tc.id, content=f"unknown tool: {tc.name}", is_error=True
                            ),
                        )
                    )
                    continue

                pre_decision = self.deps.policies.evaluate(
                    "pre_tool",
                    PolicyContext(
                        hook="pre_tool",
                        agent=self.config.id,
                        tool_schema=schema,
                        tool_call=tc,
                        user_id=ctx.user_id,
                        has_approval=False,
                    ),
                )
                if isinstance(pre_decision, Deny):
                    await self.deps.auditor.emit(
                        tenant_id=ctx.tenant_id,
                        actor=f"agent:{self.config.id}",
                        kind="policy.deny",
                        target=tc.name,
                        payload={"args": tc.arguments, "reason": pre_decision.reason},
                        severity="high",
                    )
                    tool_results.append(
                        Message(
                            role="tool",
                            tool_result=ToolResult(
                                tool_call_id=tc.id,
                                content=f"DENIED by policy: {pre_decision.reason}",
                                is_error=True,
                            ),
                        )
                    )
                    continue
                if isinstance(pre_decision, EnqueueApproval):
                    needs_approval.append(tc)
                    tool_results.append(
                        Message(
                            role="tool",
                            tool_result=ToolResult(
                                tool_call_id=tc.id,
                                content="QUEUED for human approval — skipping this turn",
                                is_error=False,
                            ),
                        )
                    )
                    continue
                # Allow or Rewrite (pre_tool rewrites of args not implemented in v1)
                connector_id, sep, _ = tc.name.partition(".")
                if not sep:
                    tool_results.append(
                        Message(
                            role="tool",
                            tool_result=ToolResult(
                                tool_call_id=tc.id,
                                content=f"malformed tool name (need <connector>.<tool>): {tc.name}",
                                is_error=True,
                            ),
                        )
                    )
                    continue
                try:
                    client: ConnectorClient = self.deps.connectors.get(connector_id)
                except KeyError as exc:
                    tool_results.append(
                        Message(
                            role="tool",
                            tool_result=ToolResult(
                                tool_call_id=tc.id, content=str(exc), is_error=True
                            ),
                        )
                    )
                    continue

                tool_labels = {**agent_labels, "tool": tc.name}
                with tracer.span("tool.invoke", attrs=tool_labels):
                    result = await client.invoke(
                        ToolInvocation(tool=tc.name.split(".", 1)[1], args=tc.arguments), ctx
                    )
                metrics.incr("tool.invocations", labels=tool_labels)
                metrics.observe("tool.latency_ms", result.latency_ms, labels=tool_labels)
                if not result.ok:
                    metrics.incr("tool.errors", labels=tool_labels)
                # post_tool policies can rewrite the result
                post_decision = self.deps.policies.evaluate(
                    "post_tool",
                    PolicyContext(
                        hook="post_tool",
                        agent=self.config.id,
                        tool_schema=schema,
                        tool_call=tc,
                        tool_result=result.output,
                    ),
                )
                content: Any = result.output
                if isinstance(post_decision, Rewrite):
                    content = post_decision.new_value
                await self.deps.auditor.emit(
                    tenant_id=ctx.tenant_id,
                    actor=f"agent:{self.config.id}",
                    kind="tool.invoke",
                    target=tc.name,
                    payload={
                        "args": tc.arguments,
                        "ok": result.ok,
                        "error": result.error,
                        "latency_ms": result.latency_ms,
                    },
                )
                tool_results.append(
                    Message(
                        role="tool",
                        tool_result=ToolResult(
                            tool_call_id=tc.id,
                            content=content if result.ok else (result.error or "error"),
                            is_error=not result.ok,
                        ),
                    )
                )
            messages.extend(tool_results)
        else:
            error = error or "max_turns_exceeded"

        latency_ms = int((time.monotonic() - t0) * 1000)
        parsed: TOut | None = None
        if error is None:
            try:
                parsed = self._parse_output(last_text)
            except (ValueError, ValidationError, json.JSONDecodeError) as exc:
                error = f"parse:{exc}"

        status = "ok"
        if error is not None:
            status = "error" if parsed is None else "partial"
        elif needs_approval:
            status = "partial"

        metrics.observe("agent.latency_ms", latency_ms, labels=agent_labels)
        metrics.incr(f"agent.status.{status}", labels=agent_labels)

        return AgentResult[TOut](
            status=status,
            output=parsed,
            raw_text=last_text,
            latency_ms=latency_ms,
            cost_usd=total_cost,
            tool_calls=total_tool_calls,
            error=error,
            needs_approval=needs_approval,
        )

    # ----- subclass hooks --------------------------------------------------

    def _system_prompt(self, *, ctx: TenantContext | None = None) -> str:
        """Look up the prompt by config.prompt path, otherwise use a stub.

        When `ctx.tenant_id` has a registered persona overlay (e.g. `jarvis`),
        it's prepended to the base prompt so the agent inherits the persona's
        voice without losing its typed output contract.
        """
        prompt = self.deps.system_prompts.get(self.config.id)
        if not prompt:
            prompt = (
                f"You are the {self.config.display_name} agent. "
                f"Produce JSON conforming to the {self.output_schema.__name__} schema. "
                "Every claim must include a sources array referring to tools you actually called."
            )
        if ctx is not None:
            persona = self.deps.system_prompts.get(f"persona:{ctx.tenant_id}")
            if persona:
                prompt = f"{persona}\n\n---\n\n{prompt}"
        return prompt

    def _parse_output(self, text: str) -> TOut:
        """Models are asked to emit JSON; tolerate ``` fences."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            # strip ```json ... ``` fences
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
            if cleaned.endswith("```"):
                cleaned = cleaned[: -len("```")]
            cleaned = cleaned.strip()
        data = json.loads(cleaned)
        return self.output_schema.model_validate(data)

    async def _collect_tools(self) -> tuple[list[ToolSchema], dict[str, ToolSchema]]:
        """Union of all tools exposed by the connectors this agent is allowed.

        Tool names are namespaced `<connector_id>.<tool>` so the agent loop can
        route them back to the right client.
        """
        out: list[ToolSchema] = []
        index: dict[str, ToolSchema] = {}
        for cid in self.config.tools.mcp:
            try:
                client = self.deps.connectors.get(cid)
            except KeyError:
                logger.warning("agent %s references unknown connector %s", self.config.id, cid)
                continue
            for t in await client.list_tools():
                namespaced = ToolSchema(
                    name=f"{cid}.{t.name}",
                    description=t.description,
                    parameters=t.parameters,
                    write=t.write,
                )
                out.append(namespaced)
                index[namespaced.name] = namespaced
        return out, index

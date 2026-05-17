"""Eval harness (spec §6, referenced from every agent's `evals.gate_score`).

A case YAML describes:
  * scripted_llm_responses — the Completions the FakeLLM should yield in order
  * scripted_tool_responses — handler outputs per (connector, tool) key
  * input — payload passed to `agent.run(input_payload=...)`
  * predicates — list of registered scorer names with optional args

Run via `EvalHarness.run_all()` to get an `EvalReport`. CI gates merges on
`report.score >= agent.evals.gate_score`.
"""

from avengers.evals.harness import (
    EvalCase,
    EvalCaseResult,
    EvalHarness,
    EvalReport,
    Scorer,
    register_scorer,
    scorer_registry,
)

__all__ = [
    "EvalCase",
    "EvalCaseResult",
    "EvalHarness",
    "EvalReport",
    "Scorer",
    "register_scorer",
    "scorer_registry",
]

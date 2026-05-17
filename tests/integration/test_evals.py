"""Eval harness runs the shipped research cases against the FakeLLM and
verifies the gate-score logic."""

from __future__ import annotations

from pathlib import Path

import yaml

from avengers.agents.research import ResearchAgent
from avengers.evals.harness import EvalCase, EvalHarness
from avengers.schemas.config import (
    AgentConfig,
    LimitsCfg,
    ModelCfg,
    ToolsCfg,
)


def _research_cfg() -> AgentConfig:
    return AgentConfig(
        id="research",
        display_name="Research",
        version="0.1.0",
        model=ModelCfg(primary="fake:m1"),
        prompt="prompts/research.md",
        input_schema="x",
        output_schema="y",
        tools=ToolsCfg(mcp=["exa_search"]),
        limits=LimitsCfg(max_turns=3, wallclock_seconds=5),
    )


def _load_cases(glob_path: Path) -> list[EvalCase]:
    return [EvalCase.model_validate(yaml.safe_load(p.read_text())) for p in sorted(glob_path.glob("*.yaml"))]


async def test_shipped_research_cases_pass():
    cases_dir = Path(__file__).resolve().parents[2] / "evals" / "cases" / "research"
    cases = _load_cases(cases_dir)
    assert len(cases) >= 3

    harness = EvalHarness(agent_cls=ResearchAgent, agent_config=_research_cfg(), cases=cases)
    report = await harness.run_all()
    assert report.score == 1.0, [c for c in report.cases if not c.passed]
    assert report.gate(0.85)


async def test_gate_fails_on_low_score():
    # Single case that's rigged to fail
    failing_case = EvalCase(
        id="failing",
        input={"trigger": "morning"},
        connectors=["exa_search"],
        scripted_llm_responses=[
            {
                "model": "m1",
                "output_text": "not json at all",
                "stop_reason": "end_turn",
                "cost_usd": 0.001,
            }
        ],
        predicates=[{"scorer": "output_parses"}, {"scorer": "no_errors"}],
    )
    harness = EvalHarness(
        agent_cls=ResearchAgent,
        agent_config=_research_cfg(),
        cases=[failing_case],
    )
    report = await harness.run_all()
    assert report.score == 0.0
    assert not report.gate(0.5)
    assert report.cases[0].failed_predicates  # both failed


async def test_unknown_scorer_marks_failure():
    case = EvalCase(
        id="bad_scorer",
        input={"trigger": "morning"},
        connectors=["exa_search"],
        scripted_llm_responses=[
            {
                "model": "m1",
                "output_text": '{"topic_deltas": [], "deep_dive": []}',
                "stop_reason": "end_turn",
                "cost_usd": 0.0,
            }
        ],
        predicates=[{"scorer": "does_not_exist"}],
    )
    harness = EvalHarness(agent_cls=ResearchAgent, agent_config=_research_cfg(), cases=[case])
    report = await harness.run_all()
    assert report.score == 0.0
    assert any("unregistered" in p for p in report.cases[0].failed_predicates)

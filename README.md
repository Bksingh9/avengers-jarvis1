# AVENGERS Platform

Multi-tenant, multi-agent daily-briefing and on-demand command system for
enterprises. Six reference specialists ship with v1 — Meetings, Markets,
Security, Research, Content, Operations — orchestrated by a Director agent.

## What's in this repo right now

This commit implements the foundation specified in SPEC.md §6–§9 plus stubs
through §11:

| Section          | Status                                                |
| ---------------- | ----------------------------------------------------- |
| §6 Repo layout   | done                                                  |
| §7 Config model  | done — Pydantic v2 models, YAML loader, hot reload    |
| §8 Domain schemas| done — tenant, user, brief, digests, audit, approvals |
| §9 Interfaces    | done — LLM, memory, identity, delivery, connector, policy |
| §10 Agents       | base class + Director + 6 specialists scaffolded      |
| §11 Workflows    | morning_brief, deep_dive, approval scaffolded         |
| §12+             | TODO                                                  |

## Quickstart (dev)

```bash
cd avengers
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
pytest -q
```

## Layout

See SPEC.md §6. Key directories:

- `config/` — tenant, agent, connector, policy YAML.
- `prompts/` — every prompt as a markdown file.
- `src/avengers/schemas/` — Pydantic models for the domain and config.
- `src/avengers/{llm,memory,identity,delivery,connectors}/` — pluggable
  adapter layers; vendor SDKs never imported outside these.
- `src/avengers/agents/` — Director + specialists.
- `src/avengers/workflows/` — Temporal workflow definitions.
- `tests/` — unit / integration / e2e.

## Adding a new agent

1. Drop `config/agents/<my_agent>.yaml`.
2. Drop `prompts/<my_agent>.md`.
3. Optionally add `config/connectors/<my_connector>.yaml` and ship its MCP image.
4. Define I/O Pydantic models under `src/avengers/schemas/custom/<my_agent>.py`.
5. Add eval cases under `evals/cases/<my_agent>/`.

The platform discovers the agent on the next config reload — no core code
changes required.

# AVENGERS Platform

Multi-tenant, multi-agent daily-briefing and on-demand command system for
enterprises. Nine specialists ship today — six reference (Meetings, Markets,
Security, Research, Content, Operations) plus three Fynd-specific (Catalog,
Inventory, Reconciliation) — orchestrated by a Director agent and rendered in
a glassmorphism Next.js dashboard that streams briefs in real time.

## Status snapshot

| Section          | Status                                                |
| ---------------- | ----------------------------------------------------- |
| §6 Repo layout   | ✅                                                     |
| §7 Config model  | ✅ Pydantic v2, YAML loader, hot reload                |
| §8 Domain schemas| ✅ tenant, user, brief, digests, audit, approvals     |
| §9 Interfaces    | ✅ LLM, memory, identity, delivery, connector, policy |
| §10 Agents       | ✅ Director + 9 specialists                            |
| §11 Workflows    | ✅ morning_brief (SSE), deep_dive, approval queue     |
| §12 Security     | ✅ OIDC, SCIM, RBAC, S3 audit (Object Lock + KMS)     |
| §13 Observability| ✅ metrics, tracing, Langfuse sink, eval harness      |
| §14 Deployment   | ✅ Terraform modules, Helm chart, Dockerfiles         |
| Dashboard        | ✅ Next.js 14 App Router, framer-motion, cmdk, SSE   |
| Playwright e2e   | ✅ 3 specs in `web/tests/e2e/`                        |

84 tests passing. Web build clean. Live-deploy path documented in `DEPLOY.md`.

## Quickstart (dev)

```bash
cd avengers
pip install fastapi 'pydantic[email]' pydantic-settings pyyaml httpx uvicorn
PYTHONPATH=src uvicorn avengers.api.__main__:app --port 8080
# separate terminal
cd web && npm install && npm run dev
# open http://localhost:3000
```

Full suite:

```bash
cd avengers
python3 -m pytest tests -q                 # 84 passing
cd web && npm run type-check && npm run build
npm run test:e2e:install && npm run test:e2e   # browser e2e
```

## One-click deploy — everything on Vercel

Frontend (Next.js dashboard) AND backend (FastAPI via Python serverless) live
in the same Vercel project. No separate backend host, no env var to wire up.

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2FBksingh9%2Favengers-jarvis&project-name=avengers-jarvis&repository-name=avengers-jarvis)

**Important:** When Vercel imports the repo, **leave the Root Directory field
empty** (don't set it to `web`). The top-level `vercel.json` builds Next.js
from `web/` and Python serverless functions from `api/` in one shot.

If you already imported with Root Directory set to `web`:
1. Open your project on vercel.com
2. **Settings → General → Root Directory** → clear the field → **Save**
3. **Deployments** → **Redeploy** the latest

After deploy succeeds:
- Dashboard: `https://<your-project>.vercel.app/dashboard`
- API: `https://<your-project>.vercel.app/api/avengers/healthz`
- Voice: tap the floating orb at the bottom-right of any page

**Step 2 — verify it works** (Playwright runs on your Mac):

```bash
cd avengers/web
npm install && npm run test:e2e:install
PLAYWRIGHT_BASE_URL=https://<your-vercel-url> npx playwright test deployed-smoke.spec.ts
```

Five checks pass: backend health, dashboard redirect, JARVIS voice orb, setup wizard, agents registry.

For the manual / advanced path (Fly.io, Helm, Terraform) see [DEPLOY.md](./DEPLOY.md).

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

# AVENGERS + JARVIS — Capabilities Catalog

A flat, scannable reference of *what the platform can actually do today*, organised by layer. The BRD lives in [`BRD.md`](./BRD.md); this file is the engineering / sales / pre-sales lookup.

**Last updated:** commit `3f665c3` · 90/90 Python tests · 11 web routes · 7 Playwright specs.

---

## Quick contents

| Section | What |
|---------|------|
| [1. Specialists](#1-specialist-agents) | The nine agents and what each one does |
| [2. LLM providers](#2-llm-providers) | Five vendor-agnostic backends |
| [3. Memory stores](#3-memory-stores) | Three plus filesystem + persona overlay |
| [4. Identity & access](#4-identity--access) | OIDC, SCIM, Static, RBAC |
| [5. Connectors](#5-data-source-connectors-mcp) | 5 live MCP-shaped connectors |
| [6. Delivery channels](#6-delivery-channels) | 7 surfaces, web + console live |
| [7. Policies](#7-policy-primitives) | The closed registry that keeps tenants safe |
| [8. Workflows](#8-workflows) | 5 production paths |
| [9. Observability](#9-observability) | Metrics + traces + LLM-call sink |
| [10. Eval harness](#10-eval-harness) | Closed scorer registry + gate scores |
| [11. JARVIS](#11-jarvis-personal-ai-layer) | Persona, voice, proactive, setup |
| [12. Web surfaces](#12-web-surfaces) | 11 prerendered routes |
| [13. APIs](#13-api-routes) | 19 backend endpoints |
| [14. Deployment](#14-deployment-targets) | Vercel + Fly + Terraform + Helm |
| [15. CI](#15-ci--testing) | pytest + Playwright |
| [16. Limits & SLAs](#16-limits--slas) | What you can promise today |

---

## 1. Specialist agents

Nine typed agents, each producing a Pydantic-validated digest. Every claim wrapped in `Cited(text, sources[≥1], confidence)` — schema-enforced.

| Agent | Display | Output schema | Connectors | Gate score | Use case |
|-------|---------|---------------|------------|------------|----------|
| `meetings` | Meetings | `MeetingDigest` (yesterday_outcomes, today_prep, action_items) | gcal | 0.85 | Calendar + transcripts + open action items |
| `markets` | Markets | `MarketDigest` (watchlist_deltas, macro_signal, new_filings) | polygon, sec_edgar | 0.85 | Watchlist, macro, filings |
| `security` | Security | `SecurityDigest` (open_criticals, anomalies, needs_approval) | splunk, crowdstrike, github_security | **0.90** | High-stakes — gates higher |
| `research` | Research | `ResearchDigest` (topic_deltas, deep_dive) | exa_search, internal_rag | 0.85 | Topic digests + on-demand deep-dives |
| `content` | Content | `ContentDigest` (drafts, publish_candidates) | cms, internal_rag | 0.80 | Drafts; publish gated by `block_writes` |
| `operations` | Operations | `OpsDigest` (kpi_deltas, queue_health, on_call) | snowflake, pagerduty, jira, datadog | 0.85 | Read-only ops in v1 |
| `catalog` | Catalog Quality | `CatalogDigest` (flagged_listings, missing_attributes, pricing_violations) | catalog_api | 0.85 | MAP violations, missing attrs |
| `inventory` | Inventory Risk | `InventoryDigest` (stockout_risks, slow_movers, transfer_recommendations) | fynd_oms, boltic | 0.85 | Stockout projection + transfer recs |
| `reconciliation` | Finance Reconciliation | `ReconciliationDigest` (settlement_mismatches, gst_anomalies, returns_liability) | fynd_oms | **0.90** | Financial-grade gate |

Each agent runs a bounded tool-use loop (`max_turns`, `wallclock_seconds`), passes every tool call through pre/post-policy hooks, and emits an audit event per invocation.

### Add a new specialist

1. Pydantic digest in `src/avengers/schemas/brief.py` (extend, don't fork)
2. 4-line `BaseAgent[<Digest>]` subclass in `src/avengers/agents/<name>.py`
3. Register the class in `bootstrap._SPECIALIST_CLASSES`
4. YAML in `config/agents/<name>.yaml`
5. Prompt in `prompts/<name>.md`
6. Add to a tenant's `agents_enabled` list

**No core code changes.** Demo: this is exactly how Catalog, Inventory, Reconciliation shipped on top of the original 6.

---

## 2. LLM providers

All sit behind `avengers.llm.base.LLMProvider` (Protocol). Vendor SDKs are imported lazily inside the adapter module only.

| Provider | Module | API surface | Status |
|----------|--------|-------------|--------|
| Anthropic Messages API | `llm/anthropic_provider.py` | tool use, JSON schema, streaming, caching, thinking | ✅ live, needs `ANTHROPIC_API_KEY` |
| AWS Bedrock | `llm/bedrock_provider.py` | InvokeModel + InvokeModelWithResponseStream | shape ready, IAM scoped to 3 model ARNs in Terraform |
| OpenAI | `llm/openai_provider.py` | tool use, JSON schema, streaming | shape ready |
| OpenRouter | `llm/openrouter_provider.py` | high-volume cheap routing | shape ready |
| Self-hosted Hermes (vLLM) | `llm/hermes_provider.py` | sovereign deployments | shape ready |
| Fake (tests) | `llm/fake_provider.py` | deterministic enqueue | ✅ |
| Demo (no-spend) | `api/__main__.py::DemoLLMProvider` | introspects system prompt, returns shaped digest | ✅ ships in `__main__` |

### Routing

`LLMRouter.complete(spec="<provider>:<model>", fallback_spec=...)` parses the provider, dispatches, retries on `LLMProviderError(retryable=True)`, accumulates cost + emits an LLM trace.

### Cost discipline

`BudgetTracker.try_charge(cost_usd, daily_cap, per_user_cap)` runs after every turn. Failed charges *don't persist* — you can't be billed for a call that was rejected.

---

## 3. Memory stores

`avengers.memory.MemoryStore` Protocol — namespaced (tenant/user/purpose), upsert/search/get/delete/health.

| Store | Status | Use case |
|-------|--------|----------|
| `InMemoryStore` | ✅ | tests, single-process dev |
| `FilesystemMemory` | ✅ | Agent-SDK-style `/memories/<tenant>/<user>/*.md` for daily handoffs |
| `PgVectorStore` | shape ready | Postgres + pgvector |
| `TurbopufferStore` | shape ready | managed vector |
| `PineconeStore` | shape ready | managed vector |

### Persona overlay (new in JARVIS layer)

`memory/<tenant>/persona.md` is loaded by `bootstrap.build_container(personas_root=…)` into `AgentDeps.system_prompts["persona:<tenant>"]`. `BaseAgent._system_prompt(ctx)` prepends it. **Every specialist for that tenant now speaks in the persona's voice without forking a single line of agent code.**

Cap Brij's persona file lives at `memory/jarvis/persona.md` and turns every agent's output into chief-of-staff voice addressed to "Cap Brij".

---

## 4. Identity & access

### Providers

| Provider | Token format | Status |
|----------|--------------|--------|
| `StaticIdentityProvider` | `user:<id>` | ✅ tests + dev |
| `OIDCProvider` | bearer access token | ✅ userinfo flow + token cache; JWKS swap-in documented |
| SCIM 2.0 | POST `/scim/v2/users` | ✅ admin-gated |
| SAML | shape ready | Phase F-1 |

### Tenant scoping

`require_tenant_ctx` FastAPI dep extracts bearer → `IdentityProvider.verify_token` → builds `TenantContext`. **Cross-tenant access returns 403 at the dependency layer** before any route logic runs.

### RBAC

`config/connectors/<id>.yaml::rbac.required_groups_any/all` is enforced *inside the connector's `invoke()`* — agents can't bypass it. Demonstrated on the JioCommerce + Catalog + Boltic + FyndOMS connectors (all gated on `fynd-internal` group).

### Dual auth (cron + user)

`/jarvis/proactive` accepts EITHER:
- `Authorization: Bearer <user-token>` (dashboard path)
- `X-Cron-Secret: <secret>` (Vercel Cron path)

Separate headers prevent collisions; cron secret is rotatable via `fly secrets set`.

---

## 5. Data-source connectors (MCP)

All implement `avengers.connectors.base.ConnectorClient` (Protocol). Today they return realistic stub payloads; swapping to live MCP servers is one PR per connector.

| Connector | Tools | Backend | RBAC default |
|-----------|-------|---------|---------------|
| `exa_search` | `search` | Exa web search | (open) |
| `fynd_oms` | `list_orders`, `fulfillment_health`, `returns_queue` | Fynd Platform OMS | `fynd-internal` |
| `boltic` | `list_pipelines`, `recent_runs`, `failed_jobs` | Boltic data integration | `fynd-internal` |
| `catalog_api` | `list_flagged` | Fynd Platform catalog | `fynd-internal` |
| `jiocommerce` | `list_orders`, `fulfillment_health`, `returns_queue`, `search_catalog`, `list_flagged` | platform.jiocommerce.io | `fynd-internal` |

### Commerce backend swap

`COMMERCE_BACKEND` env var:

| Value | Registers |
|-------|-----------|
| `fynd` (default) | `fynd_oms` only |
| `jio` | `jiocommerce` only |
| `both` | both side-by-side, agents can use either by namespace |

**Tool names are identical across `fynd_oms` and `jiocommerce`** — agents don't know which backend is live. Same prompt, same digest, swap by env.

### Adding a connector

1. `src/avengers/connectors/<name>/__init__.py` — implement `ConnectorClient`
2. `config/connectors/<name>.yaml` — declare tools + RBAC + caching
3. Register in `__main__._build()` or `bootstrap`
4. Reference from an agent's `tools.mcp` list

---

## 6. Delivery channels

`avengers.delivery.DeliveryChannel` Protocol — `deliver(user, brief, channel_cfg)` + `thread_reply(thread_ref, message)`.

| Channel | Module | Status |
|---------|--------|--------|
| Web dashboard (live SSE) | `api/routes/stream.py` | ✅ |
| `ConsoleChannel` (in-memory) | `delivery/console_channel.py` | ✅ |
| Slack (Block Kit) | `delivery/slack.py` | shape ready |
| Microsoft Teams (Adaptive Cards) | `delivery/teams.py` | shape ready |
| SES email (HTML) | `delivery/email_ses.py` | shape ready |
| SMS (Twilio) | `delivery/sms_twilio.py` | shape ready |
| Webhook | `delivery/webhook.py` | shape ready |
| Telegram (JARVIS off-machine) | spec §8 — same `/jarvis/converse` endpoint behind a bot | TODO |

`User.delivery_prefs.channels` + `quiet_hours_local` per user.

---

## 7. Policy primitives

Closed registry. Tenant YAML can never execute arbitrary code.

### Hook points

| Hook | Fires |
|------|-------|
| `pre_tool` | Before a tool invocation; can deny / enqueue approval / allow |
| `post_tool` | After a tool result; can rewrite the result |
| `pre_deliver` | Before brief delivery; can rewrite the digest |

### Decisions

`Allow | Deny(reason) | Rewrite(new_value) | EnqueueApproval(reason)`.

### Built-in conditions

| Condition | What it checks |
|-----------|----------------|
| `contains_pii` | Any arg matches email/SSN/PAN/Aadhaar/card/phone regex (ordering: specific patterns first) |
| `digest_has_unsourced_claims` | Walks the output and finds `Cited` with empty sources |
| `not_has_approval` | True when the call hasn't been pre-approved by a human |

### Built-in mutators

| Mutator | Effect |
|---------|--------|
| `drop_unsourced_claims` | Filter list-of-Cited keeping only items with ≥1 source |

### Built-in policies shipped

| Policy | Hook | Action |
|--------|------|--------|
| `no_pii_to_external_search` | `pre_tool` | `deny` if PII in args of `exa_search.search`/`news.search`/`WebSearch` |
| `cite_every_claim` | `post_tool` | `rewrite` to drop unsourced Cited items |
| `block_writes` | `pre_tool` | `enqueue_approval` for any tool with `write: true` |

### Adding a policy

1. YAML in `config/policies/<id>.yaml` with `when` / `match` / `condition` / `action` / `mutate`
2. Reload via `POST /tenants/<id>/admin/config/reload` (admin only)

---

## 8. Workflows

| Workflow | Module | Trigger | Status |
|----------|--------|---------|--------|
| `morning_brief` | `workflows/morning_brief.py` | cron or API POST | ✅ Temporal-shaped async; ports cleanly to `@workflow.defn` |
| `deep_dive` | `workflows/deep_dive.py` | user query (text or voice) | ✅ |
| Approval queue | `workflows/approval.py` | policy-driven | ✅ in-process queue with `await_decision(timeout)` + signal-resume contract |
| SSE stream brief | `api/routes/stream.py` | dashboard POST | ✅ per-section queue, `start → section×N → done` frames |
| JARVIS proactive | `api/routes/jarvis.py` | Vercel Cron at 07:00 IST | ✅ |

All workflows are best-effort: a failed specialist becomes `Section(status="error")`; the brief still ships with the rest.

---

## 9. Observability

`avengers.observability.{metrics,tracing,langfuse_sink}` — three signals, all no-op by default so library code stays import-safe in tests.

### Metrics

`Metrics` Protocol. `incr(name, value, labels)` + `observe(name, value, labels)`.

| Implementation | Use |
|----------------|-----|
| `NullMetrics` | default; zero overhead |
| `InMemoryMetrics` | tests, with inspection helpers |
| `PrometheusMetrics` | production (lazy-imports `prometheus_client`) |

### Tracing

| Implementation | Use |
|----------------|-----|
| `NullTracer` | default |
| `RecordingTracer` | tests |
| (OTel binding shape) | production: `set_tracer(otel_tracer)` |

Spans opened: `llm.call`, `tool.invoke`, `agent.run`, `morning_brief`.

### LLM-call traces

`LLMTraceSink` — Langfuse-shaped per-call records: provider, model, tokens, cost, latency, stop_reason, metadata. `LangfuseSink` lazy-imports the SDK. Failure to ship a trace is logged but **never raised** — observability must not break a brief.

### Counters emitted today

| Counter | Labels |
|---------|--------|
| `llm.calls` | provider, model, tenant |
| `llm.input_tokens` / `llm.output_tokens` / `llm.cost_usd` | provider, model, tenant |
| `llm.latency_ms` (histogram) | provider, model, tenant |
| `tool.invocations` / `tool.errors` | agent, tenant, tool |
| `tool.latency_ms` (histogram) | agent, tenant, tool |
| `agent.runs` | agent, tenant |
| `agent.status.{ok\|partial\|error}` | agent, tenant |
| `agent.latency_ms` (histogram) | agent, tenant |

---

## 10. Eval harness

`avengers.evals.EvalHarness` — drives an agent against scripted FakeLLM + FakeConnector responses, scores each case, returns `EvalReport` with `.score` + `.gate(threshold)`.

### Built-in scorers

| Scorer | Pass condition |
|--------|----------------|
| `output_parses` | `result.output is not None and status ∈ {ok, partial}` |
| `no_errors` | `status == "ok"` and `error is None` |
| `all_claims_cited` | Every `Cited` in the output has ≥1 source |
| `cost_under(usd)` | `result.cost_usd ≤ usd` |
| `latency_under(ms)` | `result.latency_ms ≤ ms` |
| `tool_called(min)` | `result.tool_calls ≥ min` |

### Shipped case sets

| Agent | Cases | Where |
|-------|-------|-------|
| `research` | 3 (happy path, empty-but-valid, cost-cap) | `evals/cases/research/*.yaml` |
| (others) | TODO ≥20/agent for GA |

### Gate enforcement

Per-agent `evals.gate_score` in YAML. CI fails the merge if `report.score < threshold`.

---

## 11. JARVIS — personal-AI layer

### Persona overlay

`memory/<tenant>/persona.md` → prepended to every agent prompt for that tenant via `BaseAgent._system_prompt(ctx)`. Cap Brij's persona makes the agents:

- Address him as "Cap Brij" every turn
- Speak in chief-of-staff voice (short, direct, no preamble)
- Lead with the answer, justify second
- Lead reversible decisions with action ("I've staged the rerun"), gate irreversible ones with approval

Verified by test that `acme` tenant agent prompts do NOT contain "Cap Brij" while `jarvis` tenant agent prompts do.

### Conversational endpoint

```http
POST /tenants/jarvis/jarvis/converse
Authorization: Bearer user:cap-brij
{
  "query": "what broke overnight?",
  "voice_mode": true
}
→
{
  "text": "Cap Brij — Boltic returns pipeline failed at 02:14...",
  "speakable": "Cap Brij — Boltic returns pipeline failed at 02 14...",
  "cost_usd": 0.0011,
  "citations": [{"connector": "boltic", "tool": "failed_jobs", "ref": "r122"}]
}
```

The `speakable` field is markdown-stripped (no `**`, ``` , `[]`, etc.) so browser TTS doesn't read out asterisks.

### Voice

Browser-native — zero API keys.

| Surface | API | Lang |
|---------|-----|------|
| Speech-to-Text | `SpeechRecognition` (webkit-prefixed where needed) | `en-IN` |
| Text-to-Speech | `SpeechSynthesis` with voice preference order: `en-GB` → `en-IN` → `en-AU` → any English | speaks `speakable` only |

Graceful fallback on browsers without support (Firefox).

### Proactive heartbeat

Vercel Cron at `30 1 * * *` (01:30 UTC = 07:00 IST) → `/api/cron/jarvis-proactive` → `POST /tenants/jarvis/jarvis/proactive` with `X-Cron-Secret`.

Returns headline + body + speakable + sections array. Dashboard's `<ProactiveBanner>` also polls this every 15 min during the day so afternoon changes don't wait until tomorrow morning.

### Setup wizard

`/setup` route — 8-step interactive tutorial:

1. Clone the repo
2. Install backend deps
3. Boot the backend
4. Boot the dashboard
5. Switch to the JARVIS tenant
6. Pick your commerce backend (Fynd / Jio / both)
7. Deploy live (Fly + Vercel)
8. Talk to JARVIS (voice)

Each step has copy-paste-ready commands with a clipboard button, an animated progress bar (persisted to the browser tab), and an optional verify hint.

---

## 12. Web surfaces

11 prerendered Next.js routes (149 kB first-load on `/dashboard`, 145 kB on `/jarvis`).

| Route | Purpose | Stack notes |
|-------|---------|-------------|
| `/` | Redirects to `/dashboard` | |
| `/dashboard` | Morning brief, six glass cards stream in via SSE, breathing-light hero, cost ticker, ⌘K command palette | framer-motion + SWR |
| `/jarvis` | Conversational thread with push-to-talk voice orb + suggestions + citation chips + proactive banner | Web Speech API |
| `/setup` | 8-step interactive tutorial wizard | |
| `/agents` | Registry of enabled specialists with model + policy badges | SWR |
| `/approvals` | HIL queue, 5-second auto-refresh, approve/deny + sonner toasts | |
| `/audit` | Placeholder card for the S3 audit live-tail (Phase 3) | |
| `/settings` | Identity, tenant caps, delivery channels | |
| `/api/cron/jarvis-proactive` | Vercel Cron entrypoint (forwards to backend with `X-Cron-Secret`) | Edge-friendly Node runtime |

UI polish that ships today:

- **Glassmorphism** on every card, dark-by-default, HSL-variable palette
- **9 per-agent accent colors** (catalog ➜ rose, inventory ➜ cyan, reconciliation ➜ green, plus the original 6)
- **Voice orb** with dual pulsing halos, state-keyed icon
- **Command palette** (⌘K, cmdk-powered) with 7 actions
- **Sonner toasts** for stream events, approval decisions, voice errors
- **Hero gradient** breathes while a brief is running, settles when done
- **Progress shimmer** on streaming section cards before they resolve

---

## 13. API routes

19 endpoints on the FastAPI control plane.

### Open

| Method | Path | What |
|--------|------|------|
| GET | `/healthz` | Liveness + counts |

### Tenant-scoped (require bearer)

| Method | Path | What |
|--------|------|------|
| GET | `/tenants/{id}` | Tenant lookup |
| GET | `/tenants/{id}/users/me` | Authenticated user echo |
| GET | `/tenants/{id}/agents` | List enabled agents |
| GET | `/tenants/{id}/agents/{agent_id}` | Agent config |
| POST | `/tenants/{id}/briefs` | Trigger morning brief now |
| GET | `/tenants/{id}/briefs/{for_date}` | Fetch a brief |
| POST | `/tenants/{id}/briefs/stream` | SSE stream of brief progress |
| GET | `/tenants/{id}/approvals` | Pending approvals |
| POST | `/tenants/{id}/approvals/{id}/decide` | Approve / deny |
| POST | `/tenants/{id}/jarvis/converse` | Conversational deep-dive (returns text + speakable + citations) |
| POST | `/tenants/{id}/jarvis/proactive` | Proactive push payload (dual auth: user bearer OR cron secret) |

### Admin-gated (require `avengers-admin` group)

| Method | Path | What |
|--------|------|------|
| POST | `/tenants/{id}/scim/v2/users` | SCIM user create/update/delete |
| POST | `/tenants/{id}/admin/config/reload` | Hot-reload YAML configs |
| GET | `/tenants/{id}/admin/budget` | Today's spend snapshot |

---

## 14. Deployment targets

| Target | Manifest | Use |
|--------|----------|-----|
| **Vercel** (web) | `web/vercel.json` + Vercel UI import | Dashboard hosting, Next.js cron |
| **Fly.io** (backend) | `fly.toml` | FastAPI control plane, Mumbai region |
| **Docker Compose** (local) | `docker-compose.dev.yml` | api + web + postgres + temporal |
| **Kubernetes / EKS** | `infra/helm/avengers/` | Production multi-tenant SaaS |
| **AWS** (full stack) | `infra/terraform/{envs/dev, modules/*}` | VPC, per-tenant KMS, S3 audit (Object Lock), Aurora Serverless v2, ECS Fargate, ALB, Bedrock IAM, Temporal |

### Terraform modules (8)

| Module | What |
|--------|------|
| `vpc` | 3-AZ with NAT |
| `kms` | Per-tenant CMK with rotation |
| `secrets` | Per-tenant Secrets Manager namespace |
| `s3-audit` | Per-tenant audit bucket with COMPLIANCE Object Lock + SSE-KMS + Glacier lifecycle |
| `aurora` | Serverless v2 Postgres with backups + final-snapshot guard |
| `ecs` | Fargate cluster, ALB with TLS-1.3, api + worker services, circuit-breaker rollback |
| `bedrock` | InvokeModel IAM scoped to 3 model ARNs (Opus, Sonnet, Haiku) |
| `temporal` | Env-var passthrough for Temporal Cloud namespace |

### Helm chart

- `deployment-api.yaml` + `deployment-worker.yaml`
- `hpa-api.yaml` (CPU-based)
- `networkpolicy.yaml` (default-deny + explicit egress: DNS, HTTPS, Postgres, Temporal-gRPC)
- `serviceaccount.yaml` (IRSA-ready)
- IRSA-friendly podSecurityContext (non-root, read-only fs, drop ALL caps)

### Dockerfiles

- `infra/docker/Dockerfile.api` — multi-stage, non-root user 10001, healthcheck against `/healthz`, single uvicorn worker (SSE-friendly)
- `infra/docker/Dockerfile.worker` — Temporal worker image
- `web/Dockerfile` — Next.js production build, non-root

### Cost (Nov 2026)

| Item | Estimate |
|------|----------|
| Vercel Hobby | $0 |
| Fly.io shared-cpu-1x 1 GB Mumbai | ~$2/month |
| LLM cost (demo provider) | $0 — DemoLLMProvider returns shaped digests |
| LLM cost (real Anthropic, single user) | $5–30/month |
| Fynd / Jio API | per your existing plan |

---

## 15. CI & testing

### Python — `pytest`

90 tests across 13 files:

| File | Tests | Covers |
|------|-------|--------|
| `tests/unit/test_schemas.py` | 5 | Cited min-length, MorningBrief shape, Decision/Section validators |
| `tests/unit/test_redact.py` | 5 | All 6 PII classes, pattern precedence, idempotence |
| `tests/unit/test_config_loader.py` | 4 | YAML validation, interpolation, recursive walk |
| `tests/unit/test_policy.py` | 7 | Allow/Deny/Rewrite/EnqueueApproval, condition matching |
| `tests/unit/test_budget.py` | 4 | Tenant + user caps, failed-charge non-persistence |
| `tests/unit/test_rbac.py` | 4 | any/all group rules, empty-permissive |
| `tests/unit/test_audit.py` | 2 | Redaction at ingest, hash stability under key order |
| `tests/unit/test_audit_s3.py` | 2 | Object Lock + KMS args via fake S3 client |
| `tests/unit/test_memory.py` | 4 | Namespace isolation, FS traversal rejection |
| `tests/unit/test_llm_router.py` | 3 | Spec parsing, dispatch, streaming |
| `tests/unit/test_identity_static.py` | 4 | verify_token, list_users, SCIM events |
| `tests/unit/test_observability.py` | 4 | Metrics counters, RecordingTracer |
| `tests/integration/test_agent_loop.py` | 3 | Two-turn dispatch, PII deny recovery, max-turns ceiling |
| `tests/integration/test_morning_brief.py` | 3 | Three specialists in parallel, kill-switch, error isolation |
| `tests/integration/test_deep_dive.py` | 1 | Cited answer from raw + structured paths |
| `tests/integration/test_approval.py` | 4 | Approve unblocks waiter, deny short-circuits, timeout, tenant filter |
| `tests/integration/test_config_e2e.py` | 1 | Shipped YAML loads, all 9 agents present, security gate=0.90 |
| `tests/integration/test_api.py` | 11 | Auth, cross-tenant 403, brief trigger+fetch, approvals, SCIM, admin |
| `tests/integration/test_oidc.py` | 4 | Claim mapping, caching, 401 propagation, custom claim |
| `tests/integration/test_stream.py` | 1 | Full SSE round-trip, 6 sections |
| `tests/integration/test_observability_wired.py` | 1 | Metrics + spans + sink fire on real run |
| `tests/integration/test_evals.py` | 3 | Shipped cases at 100%, gate fails on low score, unknown scorer marks fail |
| `tests/integration/test_fynd_tenant.py` | 4 | YAML loads, 9 specialists, SSE 9 sections, RBAC denies guest |
| `tests/integration/test_jarvis.py` | 6 | JARVIS YAML, persona loaded only for jarvis, persona in prompt, converse speakable, proactive 8 sections, cron secret guard |

### Web — Playwright

7 specs across 4 files (chromium):

| File | Tests | Covers |
|------|-------|--------|
| `dashboard.spec.ts` | 2 | Hero + brief streams; ⌘K palette |
| `agents.spec.ts` | 1 | Registry lists specialist |
| `approvals.spec.ts` | 1 | Empty-state or row |
| `jarvis.spec.ts` | 3 | Voice orb + suggestions; type+reply with citations; setup wizard 8 steps + progress |

Run locally: `npm run test:e2e:install && npm run test:e2e`. Run against deployed: `PLAYWRIGHT_BASE_URL=https://… npm run test:e2e`.

### Build verification

| Command | Pass |
|---------|------|
| `python3 -m pytest tests -q` | 90 |
| `npm run type-check` (web) | clean |
| `npm run build` (web) | 11 routes, no errors |
| `npx playwright test --list` | 7 tests discovered |

---

## 16. Limits & SLAs

### What you can promise today

| Promise | Status |
|---------|--------|
| Brief completes in ≤ 90s p95 | architecture supports; needs real load test |
| Cost per brief ≤ $0.40 p99 | enforced by `BudgetTracker` + per-agent `wallclock_seconds` |
| Every claim has at least one source | schema-enforced (`Cited.sources: Field(min_length=1)`) |
| No write to external systems without human approval | `block_writes` policy + Approval queue |
| Cross-tenant data leak is structurally impossible | per-tenant KMS + S3 bucket + namespace + `require_tenant_ctx` dep |
| Audit retained 7 years, immutable | S3 Object Lock COMPLIANCE |
| LLM provider can be swapped without code change | `LLMProvider` Protocol + tenant YAML routing |
| New agent shipped in ≤ 1 day | YAML + prompt only — Catalog/Inventory/Reconciliation proved it |
| Voice queries work in Chrome, Edge, Safari | Web Speech API; Firefox falls back to text |
| Brief survives a single specialist failure | Director is best-effort, error becomes a section status |

### What you cannot promise yet

| Gap | When |
|-----|------|
| Hard SLA on Anthropic / Bedrock cold-start latency | Phase 4 load test |
| 99.99% control plane availability | needs multi-region active-active |
| SAML SSO | Phase F-1 |
| Live audit-search UI on dashboard | Phase 3 |
| Slack / Teams / Email / SMS delivery | adapter wiring, ~1 week each |
| Real Fynd / Jio API integration | F-2: connector swap, needs credentials + scope agreement |
| ≥ 20 eval cases per agent (GA gate) | Phase 6 hardening |

---

## Appendix — file map for engineers

```
avengers/
├── BRD.md                          ← this BRD's sibling
├── CAPABILITIES.md                 ← you are here
├── SPEC.md                         ← original engineering spec
├── RELEASE_PLAN.md                 ← phased delivery plan
├── DEPLOY.md                       ← Vercel + Fly walkthrough
├── README.md                       ← quickstart
├── docker-compose.dev.yml          ← full local stack
├── fly.toml                        ← Fly.io backend
├── config/
│   ├── tenants/                    ← acme, fynd_internal, jarvis
│   ├── agents/                     ← 9 specialist configs
│   ├── connectors/                 ← 5 connector configs
│   └── policies/                   ← 3 baseline policies
├── prompts/                        ← per-agent system prompts
├── memory/jarvis/                  ← Cap Brij's persona + reference files
├── src/avengers/
│   ├── schemas/                    ← Pydantic v2 models (domain + config)
│   ├── core/                       ← tenant, policy, audit, redact, budget, rbac
│   ├── llm/                        ← provider Protocol + adapters + router
│   ├── memory/                     ← MemoryStore Protocol + implementations
│   ├── identity/                   ← IdentityProvider Protocol + OIDC + Static
│   ├── delivery/                   ← DeliveryChannel Protocol + Console
│   ├── connectors/                 ← ConnectorClient Protocol + 5 implementations
│   ├── agents/                     ← BaseAgent + Director + 9 specialists
│   ├── workflows/                  ← morning_brief, deep_dive, approval
│   ├── api/                        ← FastAPI app + 19 routes
│   ├── observability/              ← metrics, tracing, langfuse sink
│   └── evals/                      ← harness + scorer registry
├── web/
│   ├── app/                        ← Next.js App Router (11 routes)
│   ├── components/                 ← layout + brief + jarvis + ui
│   ├── lib/                        ← typed api client + auth + jarvis voice
│   ├── tests/e2e/                  ← 7 Playwright specs
│   ├── tailwind.config.ts          ← HSL palette + agent accent colors
│   ├── playwright.config.ts        ← e2e config with auto webServer
│   └── vercel.json                 ← framework + cron + SSE headers
├── infra/
│   ├── terraform/                  ← 8 modules + dev env
│   ├── helm/avengers/              ← chart + values
│   └── docker/                     ← api + worker Dockerfiles
└── tests/                          ← 90 pytest cases
```

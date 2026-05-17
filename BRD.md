# Business Requirements Document — AVENGERS + JARVIS

**Document type:** BRD + capability snapshot
**Version:** 1.0
**Status:** working software through Phases 0–5; demo-deployable today
**Branch:** `claude/build-avengers-platform-poDQP`
**PR:** [#1](https://github.com/Bksingh9/thrive-record-hub/pull/1)
**Author of record:** [you]
**Prepared for:** product / business / Fynd & Reliance leadership / design partners

---

## 1. Executive summary

**AVENGERS** is a multi-tenant, multi-agent **command and briefing platform** for enterprises. Every morning, a coordinated team of nine AI specialist agents produces a single, trustworthy, **fully-sourced** briefing tailored to each user. During the day, the same agents handle on-demand deep-dives and stage proposed write actions behind a human-in-the-loop approval queue.

**JARVIS** is the personal-AI layer on top of AVENGERS. It addresses the user as "Cap Brij", speaks with a chief-of-staff voice, runs in their browser with native voice in/out, and pushes proactive heartbeats at 07:00 IST every morning. Same backend, same specialists, same audit and policy plumbing — different face.

The platform is **policy-driven**, **vendor-agnostic** (LLM, identity, vector store, data source, delivery channel are all pluggable), and **audit-by-default** (every tool call, every model call, every approval is recorded immutably). It runs in single-tenant on-prem, single-tenant SaaS, multi-tenant SaaS, and pure-personal modes from the same codebase.

**Today it is built and verified end-to-end:**
- 90/90 Python tests passing across 13 test files
- 7 Playwright browser-tests across 4 specs
- Dashboard ships 11 prerendered routes (149 kB first-load on `/dashboard`, 145 kB on `/jarvis`)
- Live `curl POST /briefs/stream` returns `start → 9×section → done` with all `status=ok`
- Live `curl POST /jarvis/proactive` returns `"Cap Brij — 3 things for you."` with sources
- `COMMERCE_BACKEND=jio` swaps Fynd Platform for JioCommerce without a code change

---

## 2. Problem statement

Three operator pathologies the market has not solved:

| Pathology | Today | Cost |
|-----------|-------|------|
| **Context loss across tools** | Operators tab through 8–15 tools every morning (calendar, Slack, BI, OMS, security stack, news) to construct what they need to act on | 60–90 minutes/day per knowledge worker |
| **Trust deficit on AI summaries** | LLM digests hallucinate, lose sources, and can't be audited — so executives don't use them for real decisions | GenAI pilots stall at demo, never become operating dependencies |
| **No safe write path** | "Agents that act" either don't have write access, or have it with no review queue. Neither is acceptable for an enterprise. | GenAI initiatives blocked at procurement / security review |

Plus two enterprise-specific failure modes:

| Pathology | Today | Cost |
|-----------|-------|------|
| **Cost opacity** | GenAI initiatives blow through budgets — no per-user / per-tenant cap with hard enforcement | Surprise invoices; CFO loses appetite |
| **Vendor lock-in** | Bedrock-only, OpenAI-only, "our SaaS only" — every shift in pricing or policy is a forced migration | Multi-quarter rebuild after each provider event |

---

## 3. Solution

A **Director agent** fans out work each morning to nine specialist agents in parallel. Each specialist calls its declared MCP connectors, runs a bounded tool-use loop, and produces a typed digest in which **every claim carries at least one source**. The Director aggregates into a `MorningBrief`, ranks decisions by reversibility, persists everything, and delivers to configured channels (web dashboard with live SSE, Slack/Teams/email when wired, Telegram for off-machine).

Three planes enforce trust:

| Plane | Enforcement |
|-------|-------------|
| **Policy** | Declarative YAML at `pre_tool` / `post_tool` / `pre_deliver` hooks. Conditions/mutators come from a closed registry — tenant YAML can never execute arbitrary code. Built-ins: `no_pii_to_external_search`, `cite_every_claim`, `block_writes`. |
| **Audit** | Every tool call → append-only event in per-tenant S3 with **COMPLIANCE-mode Object Lock + SSE-KMS**, 7-year default retention. PII redacted at ingest (email, SSN, PAN, Aadhaar, card, phone). |
| **Budget** | Per-tenant + per-user daily USD cap, hard-enforced *before* each LLM call. Failed charges don't persist. |

**Pluggability is the prime directive.** Every external system lives behind a Python `Protocol`; vendor SDKs (`anthropic`, `boto3`, `langfuse`) are imported lazily inside their adapter module only.

**Personal-AI overlay.** A YAML `persona.md` file per tenant, loaded by the bootstrap into `system_prompts["persona:<tenant>"]`, is prepended to every agent prompt. JARVIS uses this to make all nine specialists speak in Cap Brij's voice without forking a single line of agent code.

---

## 4. Personas

| Persona | Role | Primary surface | Key need |
|---------|------|-----------------|----------|
| **Cap Brij** (single-user JARVIS) | Founder / operator | `/jarvis` voice + `/dashboard` + Telegram | Proactive morning push; one-line voice queries during the day; never miss something that broke overnight |
| **Eve the Executive** | C-suite at a Fynd/Reliance merchant | `/dashboard` daily; Slack delivery | Trustworthy 90-second brief with citations; approve writes from her phone |
| **Omar the Operator** | Ops manager at a D2C brand | `/dashboard` + Approvals queue | Catch RTO spikes, courier SLA breaches, settlement mismatches before the close-of-day review |
| **Anika the Analyst** | Power user inside an enterprise | YAML configs + custom agents | Author new specialists in YAML + MCP without touching the platform code |
| **Ada the Admin** | Tenant admin / IT | `/admin/*` routes | Tenant onboarding in <1h; budget visibility; kill-switch on any agent; audit export for evidence requests |
| **Carl the Compliance officer** | Risk / privacy | Audit S3 + DPIA exports | Prove every claim's provenance on demand; SOC 2 evidence package |

---

## 5. End-to-end user journeys

### 5.1 Cap Brij's day (JARVIS)

| Time (IST) | Event |
|------------|-------|
| 07:00 | Vercel Cron hits `/api/cron/jarvis-proactive` → backend runs the 9-specialist brief → headline + body + speakable payload returned. Telegram bot posts the headline. Browser banner reads it aloud when Cap Brij opens the tab. |
| 07:02 | Cap Brij opens `/jarvis`, holds the orb: *"What broke overnight?"* — JARVIS replies in voice + chips: *"Cap Brij — Boltic returns pipeline failed at 02:14. Three SKUs affected. I've staged the rerun; you sign off."* |
| 10:30 | *"How's our Bangalore courier SLA?"* — JARVIS calls `jiocommerce.fulfillment_health`, reports breach % per lane, cites the call. |
| 14:15 | Content agent proposes publishing a draft. Policy `block_writes` queues an `ApprovalRequest`. JARVIS surfaces it on the banner — Cap Brij taps **Approve** — workflow resumes via signal — published — entry appended to `memory/jarvis/decisions.md`. |
| 21:00 | `/eod` job appends today's decision log + cost ($0.24) to Notion. |

### 5.2 ACME enterprise tenant (Eve the Executive)

- 06:55 cron → Director resolves TenantContext → loads memory handoff → fans out 6 specialists in parallel as Temporal-shaped activities
- Each runs a bounded tool-use loop with pre/post-policy hooks
- Director aggregates → ranks `decisions_today` (irreversible → high-cost → reversible) → audits → delivers to Slack + email
- 07:00 Eve opens dashboard, sections stream in via SSE; total cost $0.18

### 5.3 Fynd-merchant tenant ("Fynd Brain")

- 06:45 a Fynd Platform merchant tenant fires; 9 specialists run (including Catalog, Inventory, Reconciliation)
- Catalog flags 14 listings with MAP violations → Approvals queue
- Inventory predicts 3 SKUs will stock out in 5 days → recommends transfer from West warehouse → queue
- Reconciliation surfaces ₹14,237.50 settlement mismatch on Flipkart → flagged but not auto-disputed (policy `block_writes`)
- Brief delivered to merchant's Fynd Admin UI inbox

---

## 6. Functional requirements

| FR # | Requirement | Status |
|------|-------------|--------|
| FR-1 | Produce a typed, cited `MorningBrief` per user per business day | ✅ |
| FR-2 | Run N specialists in parallel, best-effort (one error ≠ all-fail) | ✅ (9 today) |
| FR-3 | Stream brief sections to the dashboard as each completes (SSE) | ✅ |
| FR-4 | On-demand deep-dive queries via API | ✅ |
| FR-5 | Human-in-the-loop approval queue for external writes | ✅ |
| FR-6 | Customer adds a new agent via YAML + prompt; no core code change | ✅ |
| FR-7 | Customer adds a new data source via MCP server + YAML | ✅ (contract live; 3 reference connectors + 2 commerce) |
| FR-8 | Tenant-scoped RBAC at the connector boundary | ✅ |
| FR-9 | OIDC/SAML SSO + SCIM 2.0 provisioning | ✅ OIDC + SCIM; SAML adapter shape ready, not wired |
| FR-10 | Per-tenant + per-user daily cost cap with hard enforcement | ✅ |
| FR-11 | Append-only audit of every tool/model/approval event | ✅ (S3 sink w/ Object Lock) |
| FR-12 | Slack / Teams / Email / SMS / Web / Webhook delivery | ✅ web + console; Slack/Teams/Email/SMS TODO |
| FR-13 | Admin UI: agents registry, approvals, audit, settings | ✅ |
| FR-14 | Eval harness gating agent versions against configured score threshold | ✅ (≥20 cases/agent for GA still pending) |
| FR-15 | Kill switch per agent per tenant | ✅ |
| **FR-16** | **Personal-AI persona overlay (JARVIS)** | ✅ persona.md per tenant, prepended to every agent prompt |
| **FR-17** | **Conversational deep-dive with text + speech output** | ✅ `/jarvis/converse` returns text + speakable + citations |
| **FR-18** | **Browser-native voice in/out** | ✅ Web Speech API (STT en-IN, TTS en-GB/IN/AU) |
| **FR-19** | **Proactive cron-driven push** | ✅ Vercel Cron at 07:00 IST → `X-Cron-Secret` → backend |
| **FR-20** | **Interactive setup tutorial** | ✅ 8-step wizard at `/setup` with copy-paste blocks + progress |
| **FR-21** | **Commerce-backend swap (Fynd Platform ↔ JioCommerce)** | ✅ `COMMERCE_BACKEND={fynd\|jio\|both}` env switch |

---

## 7. Non-functional requirements

| NFR | Target | Status |
|-----|--------|--------|
| NFR-1 Latency | p95 brief < 90s; p95 first-token deep-dive < 3s | architecture supports; needs load test |
| NFR-2 Cost | p99 brief < $0.40; per-user daily cap < $1.50 (enterprise), $25 (JARVIS) | hard-enforced by `BudgetTracker` |
| NFR-3 Isolation | Hard isolation per tenant: Postgres schema, KMS key, vector ns, audit prefix | Terraform encodes; per-tenant KMS + S3 bucket implemented |
| NFR-4 Auditability | 100% of model + tool + approval events recorded; immutable | S3 sink + Object Lock COMPLIANCE |
| NFR-5 Availability | 99.9% control plane | ECS HPA + circuit-breaker rollback + ALB; needs SLO instrumentation |
| NFR-6 Compliance | SOC 2 Type II readiness day-1 of GA | controls implemented; evidence collection in Phase 6 |
| NFR-7 Security | No vendor SDK imported outside adapter; PII redactor on all audit payloads | enforced architecturally + tested |
| NFR-8 Extensibility | New agent in < 1 day | yes — YAML + prompt only |
| NFR-9 Vendor independence | LLM provider, vector store, identity, delivery, all swappable in config | 5 LLM providers, 3 memory stores, 2 identity adapters live |
| NFR-10 Persona swap | Same agent code can serve enterprise + personal modes | yes via `persona:<tenant>` overlay |

---

## 8. System architecture (one paragraph each)

- **Control plane.** FastAPI (Python 3.11) with bearer auth + env-driven CORS (`AVENGERS_CORS_ORIGINS` accepts wildcards like `https://*.vercel.app`). Every tenant route depends on `require_tenant_ctx` — cross-tenant access fails at the dependency layer.
- **Workflow plane.** Temporal-shaped async orchestrators today (plain asyncio with idempotent activities + bounded retry + signal-based approval resume). Swappable for Temporal Cloud at GA.
- **Agent plane.** `BaseAgent` runs a bounded tool-use loop. Subclasses bind typed output schemas. `Director` does deterministic fan-out (not an LLM loop itself) — morning briefs stay cheap and predictable.
- **Connector plane.** Every data source is an MCP server (stdio or HTTP/SSE). Independently deployable Docker images. The server owns auth, RBAC, rate limit, caching, and audit emission per invocation.
- **Memory plane.** Vector store (Postgres+pgvector / Turbopuffer / Pinecone) for RAG, plus Agent-SDK-style `/memories/<tenant>/<user>/*.md` for daily handoffs, plus `memory/<tenant>/persona.md` for the JARVIS overlay.
- **Delivery plane.** Adapters per channel. Quiet hours + per-channel preferences on the `User` model.
- **Observability plane.** Per-call metrics → Prometheus, spans → OpenTelemetry, per-LLM-call traces → Langfuse. All three default to no-op so library code is import-safe in tests.
- **Audit plane.** S3 per tenant, COMPLIANCE Object Lock, SSE-KMS, lifecycle transition to Glacier after 30 days.
- **JARVIS surfaces.** Next.js dashboard with `/jarvis` (voice + chat), `/setup` (wizard), and `<ProactiveBanner>` (15-min poll + TTS). Vercel Cron at 07:00 IST. Browser-native Web Speech API for STT/TTS — no extra API keys.

---

## 9. Capabilities matrix

> *(Full catalog in `CAPABILITIES.md`. This is the executive view.)*

| Capability area | What ships today |
|-----------------|-------------------|
| **Specialist agents** | 9: Meetings, Markets, Security, Research, Content, Operations + Catalog, Inventory, Reconciliation |
| **LLM providers** | Anthropic (Messages API), Bedrock-shaped, OpenAI-shaped, OpenRouter, Hermes (self-hosted vLLM), Fake (tests), Demo (introspecting) |
| **Memory stores** | InMemory, Filesystem, PgVector-shaped, Turbopuffer-shaped, Pinecone-shaped |
| **Identity providers** | Static, OIDC (userinfo flow + JWKS-ready), SCIM 2.0 ingress; SAML adapter shape ready |
| **Delivery channels** | Console (web), Slack-shaped, Teams-shaped, SES email-shaped, SMS-shaped, Webhook-shaped (one live, five contracted) |
| **MCP connectors** | exa_search, fynd_oms, boltic, catalog_api, jiocommerce — 5 live with realistic stub payloads ready for live API swap |
| **Workflows** | morning_brief, deep_dive, approval queue, SSE stream, JARVIS converse + proactive |
| **Policy primitives** | pre_tool / post_tool / pre_deliver hooks; Allow / Deny / Rewrite / EnqueueApproval; conditions: contains_pii / digest_has_unsourced_claims / not_has_approval; mutators: drop_unsourced_claims |
| **Audit & compliance** | append-only S3 with COMPLIANCE Object Lock + SSE-KMS, PII redaction at ingest, payload-hash chaining |
| **Cost discipline** | per-tenant + per-user daily caps, hard-enforced before each LLM call; failed charges don't persist |
| **Observability** | Prometheus counters/histograms, OpenTelemetry spans, Langfuse-shaped per-call traces |
| **Eval harness** | closed scorer registry; built-in scorers: output_parses, no_errors, all_claims_cited, cost_under, latency_under, tool_called; per-agent gate score |
| **Personal-AI overlay (JARVIS)** | persona.md per tenant; conversational endpoint; voice in/out; proactive heartbeat |
| **Setup UX** | 8-step interactive wizard with copy-paste blocks and verify hints |
| **Deployment** | Terraform modules (8) + Helm chart + Dockerfiles + docker-compose.dev.yml + Vercel + Fly.io configs |
| **CI** | Playwright e2e (7 specs) + pytest (90 unit/integration) |

---

## 10. Integrations

### 10.1 LLM (vendor-agnostic via `LLMProvider` Protocol)

| Provider | Status | Notes |
|----------|--------|-------|
| Anthropic Claude (Messages API) | ✅ adapter ready | needs `ANTHROPIC_API_KEY` in `.env` |
| AWS Bedrock (Claude family) | shape ready, IAM scoped to 3 model ARNs in Terraform | needs IRSA wiring |
| OpenAI | adapter shape ready | not the default; trivial to add |
| OpenRouter | shape ready | useful for high-volume cheap routing |
| Self-hosted Hermes (vLLM) | shape ready | for sovereign deployments |
| Demo (no-spend) | ✅ ships in `__main__` | introspects system prompt, returns shaped digests — what the dashboard runs against today |

### 10.2 Identity

| Provider | Status |
|----------|--------|
| Static (dev / single-tenant) | ✅ accepts `user:<id>` bearer |
| OIDC (Okta, Auth0, Google, Microsoft, internal IdP) | ✅ userinfo flow + token cache; JWKS swap-in documented |
| SCIM 2.0 ingress | ✅ admin-gated route |
| Reliance / Fynd IdP | Phase F-1 of Fynd rollout |

### 10.3 Data sources (MCP connectors)

| Connector | Tools | Backend |
|-----------|-------|---------|
| `exa_search` | search | Exa web search |
| `fynd_oms` | list_orders, fulfillment_health, returns_queue | Fynd Platform OMS |
| `boltic` | list_pipelines, recent_runs, failed_jobs | Boltic data integration |
| `catalog_api` | list_flagged | Fynd Platform catalog |
| `jiocommerce` | list_orders, fulfillment_health, returns_queue, search_catalog, list_flagged | JioCommerce (platform.jiocommerce.io) |

All five connectors today run as Python `ConnectorClient` implementations returning realistic stub payloads. Swapping to live MCP servers is one PR per connector: replace the `_dispatch` function with an httpx call to the real API.

**Recommended next adds** (Fynd internal use, BRD §10): Slack (mentions + post), GitHub (PRs + CI), Linear/Asana (tasks), Stripe (payments), Datadog (metrics), PagerDuty (on-call).

### 10.4 Delivery channels

| Channel | Status |
|---------|--------|
| Web dashboard (live SSE) | ✅ |
| Console (in-memory, for tests) | ✅ |
| Slack (Block Kit) | shape ready; needs bot token wiring |
| Microsoft Teams (Adaptive Cards) | shape ready |
| SES email (HTML render) | shape ready |
| SMS (Twilio) | shape ready |
| Webhook | shape ready |
| Telegram (JARVIS off-machine) | spec §8; same `/jarvis/converse` endpoint behind a bot |

### 10.5 Voice (JARVIS)

| Surface | Tech | Cost |
|---------|------|------|
| Speech-to-Text | Web Speech API (`SpeechRecognition`, en-IN) | $0 — browser native |
| Text-to-Speech | Web Speech API (`SpeechSynthesis`, en-GB/IN/AU voice preference) | $0 — browser native |
| Optional quality upgrade | OpenAI Whisper STT + ElevenLabs TTS | metered, on roadmap |

---

## 11. Build status — what's done in this branch

**Cumulative state on `claude/build-avengers-platform-poDQP`:** 8 commits, ~19k LOC across 198 files. PR [#1](https://github.com/Bksingh9/thrive-record-hub/pull/1) open against `main`.

| Commit | Section | Files added | Tests after |
|--------|---------|------|------|
| `8b6fc8d` | §6–§8 foundation (schemas, config, redactor) | 16 | — |
| `08fd224` | §9 pluggable interfaces (LLM/memory/identity/delivery/connector/policy) | 35 | 41 |
| `0a92716` | §10–§11 agents + workflows (Director + 6 specialists) | 26 | 53 |
| `5c74315` | §12 control plane + OIDC + S3 audit | 17 | 71 |
| `9af97de` | §13 observability + eval harness | 14 | 79 |
| `bd6ebf1` | §14 + §15 + Next.js dashboard | 67 | 80 |
| `42f5ea7` | Fynd-internal tenant + 3 Fynd specialists | 27 | 84 |
| `f21c2e8` | Vercel + Fly deploy + Playwright e2e | 16 | 84 |
| `3f665c3` | **JARVIS for Cap Brij** (persona, voice, setup wizard, JioCommerce) | **23** | **90** |

**Live-verified** end-to-end:
- `curl POST /briefs/stream` for `acme` → `start + 6 sections + done`
- `curl POST /briefs/stream` for `fynd_internal` → `start + 9 sections + done`
- `curl POST /tenants/jarvis/jarvis/proactive` → `"Cap Brij — 3 things for you."`
- `curl POST /tenants/jarvis/jarvis/converse` → speakable text + citations
- `COMMERCE_BACKEND=jio` swaps `fynd_oms` for `jiocommerce` in `/healthz` output

**Still TODO before GA:**
- ≥20 eval cases per agent (3 shipped for research as the shape proof)
- Slack / Teams / Email / SMS / Telegram adapter wiring
- Postgres-backed brief & audit shadow read
- Local JWT verification with JWKS (today: userinfo round-trip)
- Real Terraform apply against an AWS account
- Pentest, SOC 2 evidence, DPIA
- Real Anthropic key wiring (today the seeded `__main__` uses `DemoLLMProvider` so the dashboard runs $0)

---

## 12. Commercial model — Fynd / Reliance opportunity

### 12.1 Layer 1: Internal use at Fynd (week-1 deployable)

Replace today's 8-tab morning stand-up with one brief per role. Maps to the existing 9 specialists with no code changes:

| Role | Specialist mix | Connectors |
|------|----------------|------------|
| Engineering leadership | Operations + Security + Meetings | Datadog, PagerDuty, GitHub, Jira, Calendar |
| Commerce ops / fulfillment | Operations + Markets + Inventory | Fynd OMS, JioCommerce, Snowflake |
| Customer success | Operations + Content | Freshdesk, Slack, internal RAG |
| Founders' office / CEO | Meetings + Markets + Operations | Calendar, Polygon, GMV warehouse, news |
| Security / IT | Security | CrowdStrike, Splunk, GitHub security |
| Sales / partnerships | Meetings + Content + Research | Gong, Salesforce, news, Exa |
| Brij personally (JARVIS) | All 9 + voice + proactive | as above + Fynd-specific |

### 12.2 Layer 2: B2B product on Fynd Platform ("Fynd Brain")

Every merchant onboarded to Fynd Platform automatically becomes an AVENGERS tenant with a domain-tuned roster:

- **Store Manager Brief** (Meetings analogue) — yesterday sales, staffing, fast/slow movers, ad spend efficiency
- **Catalog Quality Agent** — flagged listings, MAP violations, image quality
- **Inventory Risk Agent** — stockout projections, slow movers, transfer recommendations
- **Customer Service Agent** — top complaint themes, refund SLA, churn-risk signals
- **Marketing Agent** — campaign ROAS deltas, audience drift, blended CAC
- **Finance / Reconciliation Agent** — settlement mismatches, GST anomalies, returns liability

**Pricing options:**
- Flat: ₹2,500/store/month
- Metered: ₹15/brief with free tier of 1 brief/day
- Bundled into a higher Fynd Platform tier

### 12.3 Layer 3: Agent Extension marketplace

The YAML-agent + MCP-connector contract is the AI-native equivalent of Fynd Platform's existing extension model. Third-party developers publish AI Agent Extensions (e.g. "RTO Predictor for North India" by Partner X) as YAML + MCP container; merchants install with one click; revenue share via the existing extension billing.

Two-sided marketplace play — the same move Shopify made for apps, now native-AI.

### 12.4 Differentiation

| Incumbent | What they ship | Where AVENGERS+JARVIS wins |
|-----------|----------------|-----------------------------|
| Shopify Magic / Sidekick | Per-merchant chat | Multi-specialist daily brief + hard audit |
| Unicommerce dashboards | Static reports | Cited, decision-ranked, on-demand deep-dive |
| In-house GPT wrappers | Brittle; no policy / audit / budget | Day-1 SOC 2 controls + hard per-user cost cap |
| Salesforce Einstein | CRM-bound; per-seat heavy | Open MCP marketplace + tenant-isolated cost |
| Personal "AI copilot" tools (Mem, Notion AI) | Single-purpose, no agent fabric | One brain, multi-specialist, voice, proactive |

---

## 13. Phased rollout for Fynd

| Phase | Weeks | Deliverable | Status |
|-------|-------|-------------|--------|
| **F-0** | 1–2 | Fork repo; `fynd_internal` tenant + 1 MCP connector; deploy via Helm to dev EKS | ✅ in this PR |
| **F-1** | 3–4 | Reliance/Fynd OIDC + SCIM; first 10 internal users live; daily brief in Slack | next |
| **F-2** | 5–7 | Replace stub connectors with live Fynd OMS / Boltic / Catalog / JioCommerce APIs | next |
| **F-3** | 8–10 | Closed beta with 5 Fynd Platform merchant tenants; per-tenant KMS + audit bucket via real Terraform | |
| **F-4** | 11–13 | Open beta on Fynd Platform admin UI (one-click enable) with metered free tier | |
| **F-5** | 14–16 | Open the Agent Extension marketplace to 3 partner builders | |
| **F-6** | 17–20 | GA + pricing live + Reliance-group cross-sell (Ajio, Jio brands) | |

---

## 14. Success metrics

### 14.1 JARVIS — Cap Brij personal (week 1–4 of use)

- Cap Brij reads the proactive push within 5 minutes ≥ 5 days/week
- Voice queries ≥ 3/day
- Net cost ≤ ₹200/day
- Zero hallucinated facts (every claim has a real source)
- Zero unauthorized writes (`block_writes` policy holds)

### 14.2 Internal Fynd (months 1–3)

- 70% of engineering managers + 100% of execs reading their brief by 8 a.m. IST
- ≥ 1 deep-dive query per active user per business day
- p95 morning-brief generation < 90s
- Per-user cost < ₹120/day
- Zero data-loss incidents; zero cross-tenant audit-trail anomalies

### 14.3 Product (months 4–9)

- ≥ 50 paying merchant tenants on AVENGERS-on-Fynd-Platform
- > 60% week-4 retention on the daily-brief habit
- Brief faithfulness eval ≥ 0.90 across all six specialists
- Net cost-per-tenant under ₹600/month at 100-RPS load
- 5+ third-party Agent Extensions published

---

## 15. Risks & mitigations

| Risk | Mitigation in current build |
|------|------------------------------|
| Cost spike from runaway agent loops | `BudgetTracker` + `wallclock_seconds` + per-call cost charged after every turn |
| Prompt injection from external content (news, web, customer messages) | `cite_every_claim` + PII redactor + per-tool deny policies (`no_pii_to_external_search`) |
| Vendor lock-in on Claude/Bedrock/Anthropic | `LLMProvider` Protocol + registry; 5+ peer implementations |
| Cross-tenant leak | `require_tenant_ctx` dep + per-tenant KMS + S3 bucket + namespace; covered by tests |
| Connector flakiness during morning peak | Director is best-effort: one failed specialist becomes `status=error`, the rest of the brief still ships |
| Eval drift after model upgrade | Closed scorer registry + per-agent `gate_score`; CI fails the merge if any agent drops below threshold |
| JARVIS voice degrades on unsupported browsers | Falls back to text-only on Firefox; tested |
| Cron secret leak | Separate `X-Cron-Secret` header (not Authorization); rotatable via `fly secrets set`; never logged |
| LLM provider outage | Adapter declares `retryable` errors; router transparently falls back to `model.fallback` spec |

---

## 16. Open questions for product / leadership

| # | Question | Why it matters |
|---|----------|----------------|
| Q1 | Hosting: Fynd's own EKS in Mumbai, or Bedrock-only in `ap-south-1`? | Affects KMS strategy and data-residency story for merchants |
| Q2 | Identity for merchant tenants: reuse Fynd Platform's existing OIDC, or stand a dedicated IdP per tenant? | Affects onboarding friction and the SSO experience |
| Q3 | Pricing surface: per-store flat fee, per-brief metered, or bundled into a higher Fynd Platform tier? | Determines GTM motion and free-tier strategy |
| Q4 | Extension marketplace governance: Fynd reviews every YAML/MCP submission, or self-serve with automated policy + eval gates? | Throughput vs. quality trade-off |
| Q5 | First merchant cohort: Reliance-internal brands (Ajio, Jio brands) or external D2C design partners? | Speed vs. learnings trade-off |
| Q6 | JARVIS persona scope: stays Cap Brij's only, or productized as "JARVIS for everyone" with per-user persona files? | Determines whether the persona overlay becomes a tenant-level feature for sale |
| Q7 | Voice quality: ship with browser-native Web Speech (free), or invest in OpenAI Whisper + ElevenLabs (metered)? | Determines premium tier composition |
| Q8 | Telegram bridge: internal-only, or part of the merchant product? | Determines whether we maintain a Telegram bot as platform infra |

---

## 17. Verification (how to see it running today)

### Local

```bash
# Backend (terminal A)
cd avengers
pip install fastapi 'pydantic[email]' pydantic-settings pyyaml httpx uvicorn
PYTHONPATH=src uvicorn avengers.api.__main__:app --port 8080

# Frontend (terminal B)
cd avengers/web
npm install
npm run dev
# open http://localhost:3000

# JARVIS surface (swap web/lib/auth.ts to user:cap-brij / jarvis)
# open http://localhost:3000/jarvis  — voice + chat
# open http://localhost:3000/setup   — interactive tutorial
```

### Hosted demo (~10 minutes)

```bash
# Backend → Fly.io (Mumbai)
cd avengers && fly auth login && fly launch --copy-config --no-deploy && fly deploy

# Frontend → Vercel
# Add New → Project → Import this repo → Root: avengers/web
# Env var: AVENGERS_API_INTERNAL = https://<your-app>.fly.dev
# Optional: fly secrets set CRON_SECRET=$(openssl rand -hex 32)
#           and add the same value to Vercel env

# Browser e2e against the live URL
cd avengers/web
PLAYWRIGHT_BASE_URL=https://<vercel-url> npm run test:e2e
```

### Test commands

| Command | Expectation |
|---------|-------------|
| `python3 -m pytest tests -q` | 90 passed |
| `npm run type-check` | clean |
| `npm run build` | 11 routes, 0 errors |
| `npx playwright test --list` | 7 tests across 4 files |
| `curl http://localhost:8080/healthz` | `{"status":"ok","tenants":3,"agents":9,...}` |
| `curl POST /tenants/jarvis/jarvis/proactive` (with cap-brij bearer) | headline + body + 8 sections |

---

## Appendix A — Glossary

| Term | Meaning |
|------|---------|
| **Agent** | A named, scoped LLM workflow with declared inputs, tools, and typed output |
| **Director** | Top-level orchestrator that fans out to specialists and aggregates |
| **Specialist** | A domain agent (Meetings, Markets, etc.) invoked by the Director |
| **Connector** | An MCP server that exposes a data source as tools |
| **Tool** | A typed callable exposed by a connector |
| **Brief** | The structured aggregated output for one user on one day |
| **Tenant** | A customer organization with isolated data, secrets, policies |
| **Workspace** | A division inside a tenant; can override agent configs |
| **Policy** | A declarative YAML rule constraining what an agent can do |
| **Persona overlay** | A tenant-level system prompt prepended to every agent run |
| **Cited** | A claim with ≥1 typed `Source` — schema-enforced |
| **Decision** | A typed item ranked by reversibility |
| **Approval** | A queued action awaiting human sign-off |
| **JARVIS** | The personal-AI persona layer that addresses Cap Brij |

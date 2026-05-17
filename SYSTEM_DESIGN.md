# AVENGERS + JARVIS — End-to-End System Design

**Status:** living document · synced to commit on every architectural change
**Audience:** engineering, SRE, security, data, anyone debugging or extending
**Sibling docs:** `SPEC.md` (mandate) · `BRD.md` (business) · `CAPABILITIES.md` (flat lookup) · `RELEASE_PLAN.md` (phased delivery) · `DEPLOY.md` (operational runbook)

---

## Contents

| § | Section | What you find |
|---|---------|---------------|
| 1 | [System map](#1-system-map) | One-page topology of every running piece |
| 2 | [Service catalog](#2-service-catalog) | Every service, who owns it, what it does |
| 3 | [Data engineering](#3-data-engineering) | DBs, schemas, retention, indexes, vector store |
| 4 | [API reference](#4-api-reference) | Every endpoint with method/auth/body/response |
| 5 | [Data flows](#5-data-flows-end-to-end) | Lifecycle of each major user journey |
| 6 | [Deployment topology](#6-deployment-topology) | What runs where, today vs at scale |
| 7 | [Observability](#7-observability) | Metrics, traces, audit, dashboards |
| 8 | [Security model](#8-security-model) | Authn, authz, encryption, secrets, PII |
| 9 | [Performance & SLOs](#9-performance--slos) | What we promise and how |
| 10 | [Disaster recovery](#10-disaster-recovery) | Backups, failover, rollback |
| 11 | [Cost model](#11-cost-model) | What we pay today and at scale |
| 12 | [Open items](#12-open-items--phase-3-targets) | Tracked deferrals |

---

## 1. System map

```
                                ┌──────────────────────────────────────┐
                                │           USER SURFACES              │
                                │                                      │
                ┌──────────────►│  Web dashboard (Next.js / Vercel)    │
                │               │  /jarvis · /dashboard · /agents …    │
                │               │                                      │
                │               │  Floating voice orb (web speech API) │
                │               │                                      │
                │               │  Cap Brij desktop daemon (Mac)       │
                │               │  "Hey JARVIS" wake word, anywhere    │
                │               │                                      │
                │               │  Vercel Cron @ 07:00 IST every day   │
                │               └──────────────────┬───────────────────┘
                │                                  │ HTTPS
                │                ┌─────────────────▼─────────────────┐
                │                │      CONTROL PLANE (FastAPI)      │
                │                │      Render · Singapore region    │
                │                │      Docker · 1× 512 MB instance  │
                │                │                                   │
   browser STT/TTS              │  • Auth (bearer / OIDC / cron)    │
   (Web Speech API)             │  • Cross-tenant guard             │
                │                │  • Routes:                         │
                │                │      /briefs, /briefs/stream      │
                │                │      /tenants, /agents, /users    │
                │                │      /approvals, /scim, /admin    │
                │                │      /jarvis/converse              │
                │                │      /jarvis/proactive             │
                │                └─────┬──────────────────────┬──────┘
                │                      │                      │
                │           ┌──────────▼──────────┐  ┌────────▼─────────┐
                │           │  AGENT PLANE        │  │  WORKFLOW PLANE  │
                │           │                     │  │                  │
                │           │  Director           │  │  morning_brief   │
                │           │   └─ asyncio.gather │  │  deep_dive       │
                │           │      ├─ Meetings    │  │  approval queue  │
                │           │      ├─ Markets     │  │  SSE stream      │
                │           │      ├─ Security    │  │  jarvis proactive│
                │           │      ├─ Research    │  │                  │
                │           │      ├─ Content     │  └──────────────────┘
                │           │      ├─ Operations  │
                │           │      ├─ Catalog     │
                │           │      ├─ Inventory   │
                │           │      └─ Reconciliation
                │           └─────────┬───────────┘
                │                     │
                │           ┌─────────▼─────────────────────────────┐
                │           │  CONNECTOR PLANE (MCP-shaped)         │
                │           │                                       │
                │           │  exa_search   · fynd_oms · boltic     │
                │           │  catalog_api  · jiocommerce           │
                │           │  + (future) gcal, polygon, splunk …   │
                │           └─────────┬─────────────────────────────┘
                │                     │
                │           ┌─────────▼─────────────────────────────┐
                │           │  LLM ROUTER (vendor-agnostic)          │
                │           │                                        │
                │           │  Demo (stub)  ← currently active      │
                │           │  Anthropic Messages API  ← drop-in    │
                │           │  Bedrock / OpenAI / Hermes / Fake     │
                │           └─────────┬─────────────────────────────┘
                │                     │
                │     ┌───────────────┼───────────────────────────────┐
                │     │               │                               │
                │  ┌──▼────────┐  ┌───▼────────┐  ┌─────────▼─────┐  ┌▼──────────┐
                │  │ POLICY    │  │ AUDIT      │  │ MEMORY        │  │ BUDGET    │
                │  │ ENGINE    │  │            │  │               │  │           │
                │  │ pre_tool  │  │ append-only│  │ vector (pg-   │  │ per-tenant│
                │  │ post_tool │  │ S3 Object  │  │ vector / pp / │  │ + per-user│
                │  │ pre_deliv │  │ Lock 7y    │  │ pinecone)     │  │ daily cap │
                │  └───────────┘  │ KMS / hash │  │ FS markdown   │  └───────────┘
                │                 └────────────┘  │ persona over- │
                │                                 │ lay per tenant│
                │                                 └───────────────┘
                └───────────────────────────────────────────────┘
```

**Reading the map:** every box is a service or a plane. Solid arrows are HTTP/RPC at runtime. The four boxes at the bottom — Policy / Audit / Memory / Budget — are cross-cutting; every other plane calls into them.

---

## 2. Service catalog

| Service | Tech | Host today | Owns | Stateful? |
|---------|------|------------|------|-----------|
| **Dashboard** | Next.js 14 App Router + Tailwind + framer-motion + cmdk + SWR + sonner | Vercel hobby | UI, voice orb, command palette, proactive banner | No (SSR) |
| **Control plane API** | FastAPI + Pydantic v2 + uvicorn | Render free, Singapore | All HTTP/SSE endpoints, auth, routing | In-memory caches only |
| **Director** | Python asyncio module inside the control plane | Same | Specialist fan-out, decision ranking, brief assembly | No (stateless) |
| **9 specialists** | Subclasses of `BaseAgent` | Same | Per-domain tool-use loop + typed digest | No |
| **LLM router** | `avengers.llm.router.LLMRouter` | Same | Provider selection, retry, fallback, cost accumulation | No |
| **5 MCP connectors** | Python `ConnectorClient` implementations | Same | Data-source proxying with RBAC + caching + audit | Per-tenant rate limit counters (in-memory) |
| **Policy engine** | `avengers.core.policy.PolicyEngine` | Same | Hook evaluation at pre_tool / post_tool / pre_deliver | No |
| **Approval queue** | `avengers.workflows.approval.ApprovalQueue` | Same | HIL stage for writes; resumes calling workflow on decision | **Yes — in-memory** (production: Postgres + Temporal signal) |
| **Budget tracker** | `avengers.core.budget.BudgetTracker` | Same | Per-tenant + per-user daily USD cap, hard-enforced pre-call | **Yes — in-memory** (production: Redis) |
| **Audit sink** | `avengers.core.audit.Auditor` (in-memory by default) or `S3AuditSink` (production) | Same / S3 | Append-only event store, PII-redacted at ingest, COMPLIANCE Object Lock | Yes (S3) |
| **Memory** | `MemoryStore` (InMemoryStore / PgVector / Turbopuffer / Pinecone) + FilesystemMemory | Same / FS | RAG vectors, profile facts, daily markdown handoff, persona overlay | Yes |
| **Vercel Cron** | Edge function at `/api/cron/jarvis-proactive` | Vercel | Daily 07:00 IST trigger, forwards to Render w/ X-Cron-Secret | No |
| **Desktop helper** | `jarvis-desktop/listener.py` — Python daemon | Mac via launchd | "Hey JARVIS" wake word, mic capture, TTS playback | Per-user `.env` |

### Service ownership rule

Each row owns the data it produces and the contract it exposes. No row reads from another's internal state — they communicate via the typed schemas in `src/avengers/schemas/` only. This is enforced by the Pydantic boundary.

---

## 3. Data engineering

### 3.1 Storage layers, by purpose

| Layer | Today (v0.1) | Production target | Why |
|-------|--------------|--------------------|-----|
| **Relational (tenants, users, briefs, approvals)** | In-memory dicts in `AppContainer` | Postgres 15 (Aurora Serverless v2 on AWS, or RDS, or Render Postgres) | Survive restarts, multi-replica reads, point-in-time recovery |
| **Vector (RAG, profile facts)** | `InMemoryStore` | pgvector (same Postgres) OR Turbopuffer / Pinecone if scale > 10M rows | Single source of truth; pgvector ≤ 10M, managed for higher |
| **Filesystem memory (daily handoff)** | `.memory/<tenant>/<user>/*.md` on container disk | EFS / Object Storage gateway, OR move to Postgres `text` column | Disk on Render is ephemeral; needs durable mount |
| **Audit (append-only events)** | `InMemoryAuditSink` | `S3AuditSink` → bucket per tenant, COMPLIANCE Object Lock, SSE-KMS, 7y default retention | Immutable, evidence-grade, regulator-friendly |
| **Persona / config (YAML)** | `config/` + `prompts/` + `memory/*/persona.md` shipped in Docker image | Same | Read-only at runtime, hot-reloadable via SIGHUP |
| **Budget counters** | `BudgetTracker` dict in process | Redis (single-shard sufficient up to ~5k tenants) | Atomic INCR, TTL on day rollover, shared across replicas |
| **Approval queue** | `ApprovalQueue` dict + asyncio.Future | Postgres table + Temporal signal | Survives restart, multi-replica safe, audit-traceable |

### 3.2 Relational schema (Postgres, when wired)

```sql
-- Tenant catalog. Mirrors what's in config/tenants/*.yaml at boot;
-- runtime mutations (SCIM, kill switches) write here.
CREATE TABLE tenants (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    region        TEXT NOT NULL,
    timezone      TEXT NOT NULL,
    locale        TEXT NOT NULL,
    daily_usd_cap NUMERIC(10,4) NOT NULL,
    per_user_usd_cap NUMERIC(10,4) NOT NULL,
    kms_key_arn   TEXT NOT NULL,
    audit_bucket  TEXT NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT now(),
    updated_at    TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE users (
    id          TEXT NOT NULL,
    tenant_id   TEXT NOT NULL REFERENCES tenants(id),
    email       TEXT NOT NULL,
    display_name TEXT NOT NULL,
    timezone    TEXT NOT NULL,
    groups      TEXT[] NOT NULL DEFAULT '{}',
    delivery_prefs JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (tenant_id, id)
);
CREATE INDEX users_email_idx ON users (tenant_id, email);

-- Briefs are immutable once written. Re-runs create new rows.
CREATE TABLE briefs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     TEXT NOT NULL REFERENCES tenants(id),
    user_id       TEXT NOT NULL,
    for_date      DATE NOT NULL,
    sections      JSONB NOT NULL,       -- list[Section]
    decisions     JSONB NOT NULL,       -- list[Decision]
    kill_switched TEXT[] NOT NULL,
    model_versions JSONB NOT NULL,
    total_cost_usd NUMERIC(8,5) NOT NULL,
    generated_at  TIMESTAMPTZ NOT NULL,
    FOREIGN KEY (tenant_id, user_id) REFERENCES users (tenant_id, id)
);
CREATE INDEX briefs_user_date_idx ON briefs (tenant_id, user_id, for_date DESC);

-- Approval queue. Status transitions are append-only via a partition key
-- equal to the latest decided_at; rejected races by FOR UPDATE.
CREATE TABLE approvals (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   TEXT NOT NULL REFERENCES tenants(id),
    requested_by_agent TEXT NOT NULL,
    requested_for_user TEXT NOT NULL,
    action      TEXT NOT NULL,
    payload     JSONB NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('pending','approved','denied','expired')),
    reason      TEXT,
    decided_by  TEXT,
    decided_at  TIMESTAMPTZ,
    created_at  TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX approvals_pending_idx
    ON approvals (tenant_id, created_at DESC)
    WHERE status = 'pending';

-- Optional: budget snapshots for billing/visibility (the real-time counter
-- lives in Redis; this is the daily summary written at midnight tenant-local).
CREATE TABLE budget_daily (
    tenant_id      TEXT NOT NULL REFERENCES tenants(id),
    for_date       DATE NOT NULL,
    user_id        TEXT,                -- NULL = tenant total
    spend_usd      NUMERIC(10,5) NOT NULL,
    llm_calls      INT NOT NULL,
    tool_calls     INT NOT NULL,
    PRIMARY KEY (tenant_id, for_date, COALESCE(user_id, ''))
);
```

### 3.3 Vector schema (pgvector inside same Postgres)

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE memory_items (
    namespace  TEXT NOT NULL,           -- "tenant/user/purpose" or "tenant/shared/purpose"
    id         TEXT NOT NULL,
    text       TEXT NOT NULL,
    metadata   JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding  vector(1024),            -- choose model dim (1024 = Cohere v3, 1536 = OpenAI)
    created_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (namespace, id)
);

-- HNSW index for cosine similarity, tuned for ≤ 1M rows per namespace
CREATE INDEX memory_items_emb_idx
    ON memory_items
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX memory_items_namespace_idx ON memory_items (namespace);
```

Above 10M rows or 100 QPS sustained, swap pgvector for Turbopuffer (managed, $4/M reads) or Pinecone — the `MemoryStore` Protocol means it's an adapter swap, not a code rewrite.

### 3.4 Audit store (S3)

Path: `s3://avengers-audit-<tenant>/<kind>/<sha256-of-redacted-payload>`

| Property | Value |
|----------|-------|
| Object Lock mode | **COMPLIANCE** (immutable, not even root-can-delete during retention) |
| Default retention | 7 years (configurable per tenant via `AuditCfg.retention_years`) |
| Encryption | SSE-KMS using the per-tenant CMK |
| Lifecycle | Transition to S3 Glacier after 30 days (90% storage cost reduction) |
| Bucket key | `<tenant>/<kind>/<hash>` — `kind` is one of `tool.invoke`, `model.call`, `policy.deny`, `approval.decided`, `brief.generated`, `delivery.error`, `scim.event` |
| Body | Redacted JSON payload (PII removed at ingest in `Auditor.emit`) |
| Metadata headers | `tenant-id`, `actor`, `kind`, `severity` (for catalog / search before downloading body) |
| Index | Postgres `audit_events` table with `(tenant_id, ts, kind, actor, payload_hash, payload_ref)` — payload itself stays in S3, only metadata in Postgres so searches are fast |

```sql
-- Postgres-side audit index. Body never stored here; this is just a searchable
-- catalog with pointers to S3 keys.
CREATE TABLE audit_events (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     TEXT NOT NULL REFERENCES tenants(id),
    ts            TIMESTAMPTZ NOT NULL,
    actor         TEXT NOT NULL,         -- 'user:<id>' or 'agent:<name>'
    kind          TEXT NOT NULL,
    target        TEXT NOT NULL,
    severity      TEXT NOT NULL DEFAULT 'info'
                  CHECK (severity IN ('info','warn','high','critical')),
    payload_hash  TEXT NOT NULL,         -- sha256 of redacted body
    payload_ref   TEXT NOT NULL,         -- S3 key
    correlation_id TEXT
);

CREATE INDEX audit_tenant_ts_idx     ON audit_events (tenant_id, ts DESC);
CREATE INDEX audit_actor_idx         ON audit_events (tenant_id, actor, ts DESC);
CREATE INDEX audit_correlation_idx   ON audit_events (correlation_id) WHERE correlation_id IS NOT NULL;
```

### 3.5 Filesystem memory layout

```
.memory/
└── <tenant_id>/
    └── <user_id>/
        ├── profile.md           ← static facts (loaded each morning)
        ├── yesterday_brief.md   ← written at end of each brief, read next day
        ├── deep_dives.md        ← appended per /jarvis/converse call (rolling)
        └── decisions.md         ← JARVIS-autonomous decisions (Cap Brij audit)
```

Persona overlay (tenant-level, ships in image):

```
memory/<tenant_id>/persona.md
```

For the `jarvis` tenant this contains the "Cap Brij" voice — prepended to every agent's system prompt at runtime via `BaseAgent._system_prompt(ctx)`.

### 3.6 Data retention & GDPR

| Data class | Retention | Deletion path |
|------------|-----------|---------------|
| Audit events | 7 years (Object Lock COMPLIANCE — cannot delete during retention) | After retention: Glacier expires automatically |
| Briefs (Postgres) | 90 days hot, then archive to S3 Standard-IA | `DELETE FROM briefs WHERE generated_at < now() - interval '90 days'` nightly |
| Memory items (vectors) | Indefinite while user active; purged on user-deletion event | SCIM delete event triggers `MemoryStore.delete(namespace=tenant/user/*)` |
| Filesystem memory | 30 days rolling | Nightly cleanup job |
| LLM cost counters | 90 days hot (per-day buckets) | Drop partition after 90 days |
| **PII** | Redacted at ingest, NEVER stored raw in audit | N/A — never written |
| **GDPR right-to-erasure** | Per-tenant DELETE: `users` row + cascade vector namespace + tombstone in audit (audit ITSELF is not deleted due to compliance lock; only the user reference is anonymized in the index — the immutable S3 object stays for the legal retention period) |

---

## 4. API reference

### 4.1 Conventions

| Aspect | Value |
|--------|-------|
| Base URL (Render) | `https://avengers-api-k2x6.onrender.com` |
| Base URL (via Vercel) | `https://<your-app>.vercel.app/api/avengers` (rewritten internally) |
| Auth | `Authorization: Bearer <token>` — token is OIDC access token in prod, `user:<id>` in dev |
| Tenant scoping | Encoded in path (`/tenants/{tenant_id}/...`). Cross-tenant access fails at FastAPI dep layer with 403 |
| Content type | `application/json` request, `application/json` response; SSE responses are `text/event-stream` |
| Error format | `{"detail": "<reason>"}` with HTTP status |
| Idempotency | Reads are idempotent; writes (POST) currently are not but accept an optional `X-Idempotency-Key` header — production wiring TODO |
| Rate limit | None enforced today; production target 100 RPS/tenant on free, 1000 RPS on paid |

### 4.2 Endpoint table (alphabetical by path)

| Method | Path | Auth | Purpose | Returns |
|--------|------|------|---------|---------|
| GET  | `/` | open | Friendly root: status + endpoint map + demo tokens | JSON |
| GET  | `/healthz` | open | Liveness probe; used by Render healthcheck | `{"status":"ok",...}` |
| GET  | `/tenants/{tenant_id}` | bearer | Tenant lookup | `Tenant` model |
| GET  | `/tenants/{tenant_id}/users/me` | bearer | Authenticated user echo | `User` model |
| GET  | `/tenants/{tenant_id}/agents` | bearer | List enabled agents for the tenant | `AgentSummary[]` |
| GET  | `/tenants/{tenant_id}/agents/{agent_id}` | bearer | Full agent config | `AgentConfig` |
| POST | `/tenants/{tenant_id}/briefs` | bearer | Generate today's brief synchronously | `MorningBrief` |
| GET  | `/tenants/{tenant_id}/briefs/{for_date}` | bearer | Fetch a brief by date | `MorningBrief` |
| POST | `/tenants/{tenant_id}/briefs/stream` | bearer | SSE stream of brief section-by-section | `text/event-stream` |
| GET  | `/tenants/{tenant_id}/approvals` | bearer | List pending approvals | `ApprovalRequest[]` |
| POST | `/tenants/{tenant_id}/approvals/{request_id}/decide` | bearer | Approve / deny | `ApprovalRequest` |
| POST | `/tenants/{tenant_id}/jarvis/converse` | bearer | Conversational deep-dive (text + speakable + citations) | `ConverseResponse` |
| POST | `/tenants/{tenant_id}/jarvis/proactive` | bearer OR X-Cron-Secret | Proactive push payload (headline / body / sections) | `ProactiveResponse` |
| POST | `/tenants/{tenant_id}/scim/v2/users` | admin bearer | SCIM user create/update/delete | `{accepted, id, op}` |
| POST | `/tenants/{tenant_id}/admin/config/reload` | admin bearer | Hot-reload YAML configs | `{ok, counts}` |
| GET  | `/tenants/{tenant_id}/admin/budget` | admin bearer | Today's spend snapshot | `BudgetSnapshot` |
| GET  | `/docs` | open | OpenAPI Swagger UI | HTML |
| GET  | `/openapi.json` | open | OpenAPI spec | JSON |

### 4.3 Request / response payloads (the ones you'll use most)

#### `POST /tenants/{id}/briefs/stream` (SSE)

Request:
```json
{ "for_date": "2026-05-17" }
```

Response (event-stream):
```
event: start
data: {"for_date":"2026-05-17","agents":["meetings","markets",...],"tenant":"jarvis"}

event: section
data: {"agent":"meetings","status":"ok","digest":{...},"cost_usd":0.001,"latency_ms":1240,"error":null}

event: section
data: {"agent":"markets","status":"ok","digest":{...},"cost_usd":0.001,"latency_ms":1100}

... (one event per specialist as it finishes)

event: done
data: {"for_date":"2026-05-17","sections":[...],"total_cost_usd":0.012}
```

#### `POST /tenants/{id}/jarvis/converse`

Request:
```json
{ "query": "what broke overnight?", "voice_mode": true }
```

Response:
```json
{
  "text": "Cap Brij — Boltic returns pipeline failed at 02:14...",
  "speakable": "Cap Brij Boltic returns pipeline failed at 02 14...",
  "cost_usd": 0.0011,
  "citations": [
    { "connector": "boltic", "tool": "failed_jobs", "ref": "r122" }
  ]
}
```

#### `POST /tenants/{id}/jarvis/proactive`

Headers: either `Authorization: Bearer <user>` or `X-Cron-Secret: <secret>`. Request body: `{}`.

Response:
```json
{
  "headline": "Cap Brij — 3 things for you.",
  "body": "• catalog: 14 MAP violations  • inventory: 3 stockouts in 5d  • reconciliation: ₹14,237 settlement mismatch",
  "speakable": "Cap Brij 3 things for you. catalog ...",
  "sections": [{"agent":"meetings","status":"ok","cost_usd":0.001}, ...],
  "total_cost_usd": 0.012
}
```

#### `POST /tenants/{id}/approvals/{request_id}/decide`

Request:
```json
{ "decision": "approved", "reason": "lgtm" }
```

Response: the updated `ApprovalRequest`.

---

## 5. Data flows (end-to-end)

### 5.1 Morning brief — the headline flow

```
T-30s          Vercel Cron @ 01:30 UTC / 07:00 IST fires.
                  ↓ GET /api/cron/jarvis-proactive (with Authorization: Bearer CRON_SECRET)
T-30s          Vercel Edge Function executes.
                  ↓ POST https://avengers-api-k2x6.onrender.com/tenants/jarvis/jarvis/proactive
                    Headers: { "X-Cron-Secret": <secret> }
T-29s          FastAPI auth dep (`_require_user_or_cron`) accepts via X-Cron-Secret.
                  ↓ build TenantContext with system:cron user
T-29s          DirectorInput { user_id, tenant_id, for_date=today, trigger=morning }
                  ↓ Director.run_morning(input, ctx)
T-29s          For each agent in tenant.agents_enabled (parallel):
                  ├─ MeetingsAgent.run(input, ctx)
                  │     ↓ collect_tools → exa_search.search, gcal.list_events
                  │     ↓ LLMRouter.complete(spec="anthropic:claude-sonnet-4-6", messages, tools)
                  │     ↓ pre_tool policy (no_pii_to_external_search) → Allow
                  │     ↓ tool invoke → audit
                  │     ↓ post_tool policy (cite_every_claim) → Allow
                  │     ↓ feed result back → LLM → typed digest
                  │     ↓ MeetingDigest output
                  ├─ MarketsAgent.run … (same loop)
                  ├─ … (7 more, in parallel)
                  └─ ReconciliationAgent.run …
T-15s          asyncio.gather joins. Director assembles MorningBrief:
                  ├─ aggregate sections (status / digest / cost / latency)
                  ├─ rank decisions: irreversible → high_cost → reversible
                  ├─ total_cost_usd = sum(section.cost_usd)
                  └─ model_versions = {agent: model_spec}
T-14s          Auditor.emit(kind="brief.generated", payload_hash=sha256(redacted),
                              payload_ref="<bucket>/<tenant>/brief.generated/<hash>")
                  ↓ S3 PutObject with Object Lock COMPLIANCE
T-14s          BudgetTracker.try_charge for each LLM call's cost (already done per-turn)
T-13s          FilesystemMemory.write("yesterday_brief.md") for tomorrow's handoff
T-13s          Delivery to user.delivery_prefs.channels:
                  ├─ console (in-memory log)
                  ├─ telegram (when wired)
                  └─ email/slack (when wired)
T-13s          Shape into ProactiveResponse {headline, body, speakable, sections}.
                  ↓ return through Vercel back to Cron logs
T-0            Cap Brij opens dashboard. SWR cache refresh fires:
                  ↓ /tenants/jarvis/briefs/today returns the brief
                  ↓ React renders 9 glass cards with status badges
                  ↓ ProactiveBanner polls /jarvis/proactive every 15 min
```

**Why best-effort:** if any specialist throws, the Director records `Section(status="error", error=str(exc))` and continues. The brief is shipped with `partial` status — never all-or-nothing.

### 5.2 Deep-dive via voice from the desktop helper

```
T+0     Cap Brij says "Hey JARVIS, what broke overnight?"
        ↓ jarvis-desktop/listener.py — SpeechRecognition phrase loop catches it
T+0.1   matches_wake() → True. macOS `say "Yes Cap Brij."`
T+0.5   sounddevice records 8 seconds of mic audio → WAV
T+8.5   sr.recognize_google(audio, language="en-IN") → "what broke overnight"
T+9     requests.post(
            f"{JARVIS_API_BASE}/tenants/jarvis/jarvis/converse",
            json={"query": "what broke overnight", "voice_mode": True},
            headers={"Authorization": "Bearer user:cap-brij"},
        )
T+9     Render: FastAPI route /jarvis/converse
            ↓ require_tenant_ctx → verify token → User
            ↓ run_deep_dive(agent=research_agent, query, user_id, ctx)
            ↓ ResearchAgent.run(input_payload={trigger:"on_demand", query}, ctx)
                ├─ collect connectors → [exa_search]
                ├─ LLMRouter.complete(...)
                │   - persona overlay prepended for jarvis tenant ("Cap Brij")
                ├─ tool invoke → exa_search.search
                ├─ feed result back
                └─ ResearchDigest output (deep_dive: [Cited])
T+11    Reshape into ConverseResponse {text, speakable, cost_usd, citations}
        ↓ speakable is markdown-stripped (no **, no `, no [], no #)
T+11    JSON response back to Mac
T+11    listener.py extracts r["speakable"] → subprocess.Popen(["say", "-v", "Daniel", text])
T+11    macOS TTS plays through speakers
T+14    "Cap Brij — Boltic returns pipeline failed at 02:14. Three SKUs affected."
T+14    Loop back to listening
```

### 5.3 Approval flow (HIL write gate)

```
Step 1  ContentAgent decides to publish a draft.
Step 2  pre_tool policy `block_writes` matches:
            match: { tool.write: true }
            condition: not_has_approval
            action: enqueue_approval
        → returns EnqueueApproval(reason="Write requires approval")
Step 3  BaseAgent records `needs_approval` in the AgentResult and
        continues without invoking the tool.
Step 4  Director aggregates the brief with Section(status="partial",
        digest containing the pending approval).
Step 5  Caller (workflow) creates ApprovalRequest in the queue:
            POST internal: queue.enqueue(...)
Step 6  Notification fires through user's delivery channels
        (Slack message with Approve / Deny buttons; future).
Step 7  User taps Approve in the dashboard:
            POST /tenants/{id}/approvals/{request_id}/decide
            { "decision": "approved", "reason": "lgtm" }
Step 8  ApprovalQueue.decide()
            ├─ updates row to status=approved, decided_by, decided_at
            ├─ resolves the asyncio.Future the original caller was awaiting
            └─ Auditor.emit(kind="approval.decided")
Step 9  Calling workflow resumes, retries the original tool call with
        has_approval=True; policy now allows.
```

### 5.4 Audit append (every event)

```
Caller   →  Auditor.emit(tenant_id, actor, kind, target, payload, severity)
            ↓
            1. redact = avengers.core.redact.redact(json.dumps(payload, sort_keys=True))
            2. payload_hash = sha256(redact.text.encode()).hexdigest()
            3. payload_ref = f"{tenant_id}/{kind}/{payload_hash}"
            4. Create AuditEvent {id, ts, tenant_id, actor, kind, target,
                                  payload_hash, payload_ref, severity}
            5. await sink.write(event, redact.text)
                ├─ InMemoryAuditSink — appends to in-process list (tests)
                └─ S3AuditSink — boto3 put_object with:
                    * Bucket: avengers-audit-<tenant>
                    * Key: <payload_ref>
                    * ObjectLockMode: COMPLIANCE
                    * ObjectLockRetainUntilDate: now + 7y
                    * ServerSideEncryption: aws:kms
                    * SSEKMSKeyId: <per-tenant CMK arn>
                    * Metadata: tenant-id, kind, severity, actor
            6. Logged at INFO via structlog
```

Searchability: the parallel Postgres `audit_events` table (§3.4) contains the metadata for fast queries; downloading the body from S3 only happens when an evidence request comes in.

---

## 6. Deployment topology

### 6.1 Today (v0.1, what's actually live)

| Component | Host | URL / Path | Region | Plan / Cost |
|-----------|------|------------|--------|-------------|
| Web dashboard | Vercel | `https://avengers-jarvis1-git-main-trends-nps.vercel.app` | Auto (global edge) | Hobby — $0 |
| Backend API | Render | `https://avengers-api-k2x6.onrender.com` | Singapore | Free — $0 (sleeps after 15 min idle, 10s cold-start) |
| Vercel Cron | Vercel Edge | `/api/cron/jarvis-proactive` | Edge | $0 |
| Audit | In-memory (RAM, lost on restart) | n/a | n/a | $0 |
| Postgres | None yet — in-memory dicts | n/a | n/a | $0 |
| Memory | Filesystem in container (`.memory/`) — ephemeral | n/a | n/a | $0 |
| LLM | `DemoLLMProvider` stub (shaped responses) | n/a | n/a | $0 |
| Desktop helper | Mac launchd | `~/Library/LaunchAgents/com.capbrij.jarvis.plist` | local | $0 |

**Total monthly cost as of today: $0.** This is the demo configuration. For production hardening go to §6.2.

### 6.2 Production target (Phase 3+)

| Component | Host | Region | Plan | Est cost / mo |
|-----------|------|--------|------|---------------|
| Web dashboard | Vercel Pro | Global edge | Pro — $20/seat | $20 |
| Backend API | AWS ECS Fargate or Render Starter | `ap-south-1` (Mumbai) | 2 vCPU / 4 GB, 2 replicas | $70 |
| Postgres | Aurora Serverless v2 | Same | 0.5–8 ACU autoscale | $50 idle, ~$200 active |
| Vector store | pgvector inside Aurora | Same | included | $0 |
| Redis | ElastiCache | Same | t4g.micro | $13 |
| Temporal | Temporal Cloud | Same | Starter | $200 |
| S3 audit | AWS S3 | Same | Object Lock + Glacier | $1 / 100 GB |
| KMS | AWS KMS | Same | 1 CMK per tenant | $1 / tenant |
| Bedrock (LLM) | AWS Bedrock | Same | Pay per token | per use |
| Observability | Langfuse + Grafana Cloud | Hosted | Free tier sufficient < 100k events | $0 → $50 |
| **Total fixed** | | | | **~$350/mo + per-tenant overhead** |

### 6.3 Topology diagram (production target)

```
                          INTERNET
                              │
                              ▼
                   ┌─────────────────────┐
                   │  CloudFront / Vercel│
                   │  global edge        │
                   └──────────┬──────────┘
                              │
              ┌───────────────┴──────────────────┐
              │                                  │
       ┌──────▼──────┐                  ┌────────▼──────────┐
       │  Vercel     │                  │   AWS ALB         │
       │  (Next.js)  │                  │   ap-south-1      │
       └──────┬──────┘                  └────────┬──────────┘
              │                                  │
              │ rewrite /api/avengers/*          │
              │  → AVENGERS_API_INTERNAL         │
              │                                  ▼
              │                       ┌──────────────────────┐
              └──────────────────────►│  ECS Fargate         │
                                      │  api task (×2-N)     │
                                      │  worker task (×2-N)  │
                                      └────────┬─────────────┘
                                               │
              ┌────────────────────────────────┼────────────────────────┐
              │                                │                        │
       ┌──────▼─────┐  ┌──────▼──────┐  ┌──────▼──────┐  ┌─────▼───────┐
       │ Aurora     │  │ ElastiCache │  │ Bedrock     │  │ S3 audit    │
       │ Serverless │  │ Redis       │  │ AgentCore   │  │ Object Lock │
       │ + pgvector │  │ (budget,    │  │ (Claude)    │  │ per tenant  │
       │            │  │  approvals) │  │             │  │             │
       └────────────┘  └─────────────┘  └─────────────┘  └─────────────┘
                              │
                       ┌──────▼──────┐
                       │ Temporal    │
                       │ Cloud       │
                       │ (durable    │
                       │  workflows) │
                       └─────────────┘
```

### 6.4 Build & release pipeline

```
git push to main
       │
       ▼
   GitHub
       │
       ├──webhook──► Vercel (auto deploys web/)
       │              │
       │              ├─ npm install (root, web/)
       │              ├─ next build
       │              ├─ if green: promote to production alias
       │              └─ env: AVENGERS_API_INTERNAL → backend URL
       │
       └──webhook──► Render (auto deploys infra/docker/Dockerfile.api)
                      │
                      ├─ docker build (multistage)
                      ├─ pip install -e ".[anthropic,bedrock,postgres,observability]"
                      ├─ healthcheck against /healthz
                      ├─ if green: promote to production
                      └─ env: AVENGERS_CORS_ORIGINS, COMMERCE_BACKEND, CRON_SECRET
```

For production AWS, the equivalent: GitHub Actions → ECR push → ECS update-service → CodeDeploy with circuit-breaker rollback. Terraform modules for this are in `infra/terraform/` (8 modules, dev env wired).

---

## 7. Observability

### 7.1 Three signals, no-op by default

| Signal | Backend today | Backend production | Surface |
|--------|---------------|--------------------|---------|
| Metrics | `NullMetrics` (no-op) | Prometheus → Grafana Cloud | Counters, histograms, gauges |
| Traces | `NullTracer` (no-op) | OpenTelemetry → Honeycomb / Grafana | Per-LLM-call, per-tool-call, per-workflow spans |
| LLM traces | `NullLLMTraceSink` ring buffer | Langfuse | Per-call provider/model/tokens/cost/latency record |

All three default to no-op so library code is safe to import in any context, including tests. Production binds happen at startup in `__main__.py` via `set_metrics()` / `set_tracer()` / `set_sink()`.

### 7.2 Metrics actually emitted (label dimensions in `[brackets]`)

```
llm.calls          counter  [provider, model, tenant]
llm.input_tokens   counter  [provider, model, tenant]
llm.output_tokens  counter  [provider, model, tenant]
llm.cost_usd       counter  [provider, model, tenant]
llm.latency_ms     histogram [provider, model, tenant]

tool.invocations   counter  [agent, tenant, tool]
tool.errors        counter  [agent, tenant, tool]
tool.latency_ms    histogram [agent, tenant, tool]

agent.runs         counter  [agent, tenant]
agent.latency_ms   histogram [agent, tenant]
agent.status.ok       counter [agent, tenant]
agent.status.partial  counter [agent, tenant]
agent.status.error    counter [agent, tenant]
```

### 7.3 Standard dashboards (Grafana, when wired)

| Dashboard | Panels |
|-----------|--------|
| **Cost** | $/tenant/day (line), $/user/day (line), cost variance vs 7d avg (bar), top 10 most expensive briefs (table) |
| **Latency** | p50/p95/p99 of `agent.latency_ms` per agent, brief end-to-end (sum of section latencies), LLM provider response time |
| **Health** | `agent.status.ok / partial / error` percentages per agent (stacked), tool error rate per connector, healthz uptime |
| **Voice** | `/jarvis/converse` calls/day, average response size (chars), wake-word fire rate per active user/day (from desktop helper logs) |

### 7.4 Logs

| Source | Format | Destination today | Destination production |
|--------|--------|--------------------|-------------------------|
| FastAPI app | structlog JSON | stdout → Render logs | CloudWatch / Loki |
| Desktop helper | stdlib logging text | `/tmp/jarvis-desktop.log` | local only |
| Vercel functions | Vercel default | Vercel logs UI | + drain to Loki via Vercel Log Drains |
| Audit | append-only, never deleted | InMemorySink + S3 | S3 only |

---

## 8. Security model

### 8.1 Auth layers

```
[Caller]                                  [Verification]                         [Authorization]
────────                                  ──────────────                         ───────────────
Browser    ──Bearer <oidc-access-token>──► IdentityProvider.verify_token        ┌─ groups in
                                              ↓                                  │  bearer
                                           returns User                          │
                                              ↓                                  ▼
                                           require_tenant_ctx                   tenant scope
                                              ↓                                  │
                                           cross-tenant check (path vs user)    │
                                              ↓                                  ▼
                                           passes → route handler ─────────────► RBAC at connector
                                                                                  ├─ rbac.check()
                                                                                  └─ raise RBACDenied

Vercel Cron ─Authorization: Bearer CRON_SECRET─► Vercel Edge fn
                              ↓
                          X-Cron-Secret: CRON_SECRET to Render
                              ↓
                          _require_user_or_cron dep:
                              if X-Cron-Secret matches → system:cron user (admin groups)
                              else → fall through to bearer auth

Desktop    ──Bearer user:cap-brij──► StaticIdentityProvider (dev)
helper                                  ↓
                                      User cap-brij (jarvis tenant, admin groups)
```

In production, the dev `Bearer user:<id>` tokens are replaced by real OIDC access tokens from your IdP (Okta, Auth0, Google, Reliance/Fynd OIDC). `OIDCProvider.verify_token` does a userinfo round-trip; cached for the token's lifetime.

### 8.2 Encryption

| Data at rest | What |
|--------------|------|
| Aurora Postgres | AES-256 via AWS-managed KMS, default |
| S3 audit | SSE-KMS, per-tenant CMK |
| ElastiCache | encryption-in-transit via TLS, encryption-at-rest via KMS |
| Vercel storage | Vercel default AES-256 |
| Render disk | Render default AES-256 |

| Data in transit | What |
|-----------------|------|
| All HTTPS | TLS 1.3 enforced at ALB / Vercel / Render edge |
| Aurora connection | TLS, certificate verified by Postgres client |
| Bedrock calls | AWS SigV4 signed, TLS 1.3 |
| Internal RPC | always over the VPC, TLS even inside |

### 8.3 Secret management

| Secret class | Today | Production |
|--------------|-------|------------|
| LLM API keys (Anthropic, OpenAI, etc.) | Env var on Render | AWS Secrets Manager, per-tenant namespace |
| CRON_SECRET | Render auto-generated, env var | Same model, rotated quarterly |
| OIDC client secrets | Env var | Secrets Manager |
| Postgres passwords | Render-managed | RDS-managed master password |
| KMS keys | n/a | One CMK per tenant, rotation on |

**Rule:** secrets NEVER appear in:
- `CLAUDE.md` / persona files
- `config/` YAML
- Git history
- Logs (PII redactor catches them at audit; structlog redacts at log)

### 8.4 PII redaction

Implemented in `avengers/core/redact.py`. Six classes, ordered most-specific-first:

| Class | Regex (simplified) | Replacement |
|-------|---------------------|-------------|
| EMAIL | `[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}` | `<EMAIL>` |
| SSN | `\b\d{3}-\d{2}-\d{4}\b` | `<SSN>` |
| PAN | `\b[A-Z]{5}[0-9]{4}[A-Z]\b` | `<PAN>` |
| CARD | `\b(?:\d[ -]*?){13,19}\b` | `<CARD>` |
| AADHAAR | `\b\d{4}\s?\d{4}\s?\d{4}\b` | `<AADHAAR>` |
| PHONE | `\+?\d[\d\s().-]{7,}\d` | `<PHONE>` |

Runs at audit ingest (every `Auditor.emit`) AND in the `no_pii_to_external_search` policy (blocks PII from being sent to external web search).

### 8.5 Threat model (high level)

| Threat | Mitigation |
|--------|------------|
| Cross-tenant data leak | `require_tenant_ctx` dep + per-tenant KMS + S3 bucket + Postgres schema |
| Prompt injection from external content | `cite_every_claim` requires source for every digest item; PII redactor cleans audit; `no_pii_to_external_search` blocks PII from going to web tools |
| Compromised LLM API key | Secrets Manager rotation; key never in repo; budget cap limits damage |
| Compromised admin token | Admin actions are audited; SCIM events trigger Slack notification (TODO) |
| Runaway agent loop | `max_turns` + `wallclock_seconds` per agent; `BudgetTracker` hard cap before each LLM call |
| DoS | Rate limit per connector (in connector RBAC config); CloudFront / Vercel edge limits |
| Supply chain (dep CVE) | `pip-audit` in CI; `dependabot` on the repo; `pin == versions` in `requirements.txt` |
| Audit-trail tampering | S3 Object Lock COMPLIANCE: not even root account can delete during retention |

---

## 9. Performance & SLOs

### 9.1 Today (free-tier limits)

| Metric | Today | Cause |
|--------|-------|-------|
| Cold-start | ~10s | Render free tier idle-shutdown after 15 min |
| Warm latency p95 | <2s for `/healthz` | FastAPI startup is fast once warm |
| Brief generation p95 | ~3s (DemoLLMProvider) | Stub returns instantly; real LLM would be 30–60s |
| Concurrent briefs | ~10 | Single 512 MB Render instance |

### 9.2 Production SLO targets

| SLO | Target | Measured by | Alert |
|-----|--------|-------------|-------|
| `GET /healthz` availability | 99.9% / 30d | Synthetic monitor every 1 min | Page on 5+ min down |
| Brief end-to-end p95 | < 90s | `agent.latency_ms` sum per brief | Grafana alert at p95 > 75s |
| Deep-dive first-token p95 | < 3s | Streaming start latency | Grafana alert at p95 > 2.5s |
| Brief cost p99 | < $0.40 | `llm.cost_usd` sum per brief | Daily report; auto-throttle at $0.50 |
| Eval gate score | ≥ agent's `gate_score` | CI on every PR | Block merge on regression |
| Zero data-loss incidents | 0 / quarter | Audit anomaly detection | Page immediately on any |
| Mean time to mitigate prompt-injection regression | ≤ 24h | Time from detection to deploy | Quarterly review |

### 9.3 Scaling milestones

| Stage | Tenants | Daily briefs | Architecture |
|-------|---------|--------------|--------------|
| Dev (today) | 3 | <100 | 1× Render free + Vercel hobby |
| Internal beta (week 1-4) | 10 | 1k | 1× Render starter + Vercel pro |
| Closed beta (week 5-12) | 100 | 10k | ECS Fargate 2 replicas, Aurora 0.5-2 ACU |
| Open beta (month 3-6) | 1k | 100k | ECS 4-10 replicas (HPA), Aurora 2-8 ACU, Redis t4g.small |
| GA (month 6+) | 10k | 1M+ | ECS 10-50 replicas, Aurora 4-32 ACU, Bedrock provisioned throughput |

---

## 10. Disaster recovery

### 10.1 RPO / RTO targets

| Data class | RPO | RTO | How |
|------------|-----|-----|-----|
| Audit (S3 Object Lock) | 0 (object replicated across AZs) | 0 (read directly from S3 from anywhere) | AWS S3 11 9s durability |
| Postgres | ≤ 5 min (continuous WAL backup) | ≤ 15 min | Aurora automatic backups + cross-region snapshot |
| Vector store (in pgvector) | Same as Postgres | Same | Same |
| YAML config | ≤ 0 (in git, immutable) | ≤ 5 min (Helm rollback) | Source-of-truth in git |
| Persona / memory markdown | 1 day (nightly sync) | 1 hour | EFS replicated, or git-tracked |
| Live state (queues, budget counters) | Acceptable loss | < 1 min | Redis Multi-AZ; on failover, counters reset to last-checkpoint (15 min granularity) |

### 10.2 Rollback playbook

| Surface | How | Time | Verify |
|---------|-----|------|--------|
| Render service | Render UI → previous deploy → Rollback | < 30s | `/healthz` returns expected JSON |
| Vercel project | Vercel UI → Deployments → previous Ready → Promote | < 1 min | `/dashboard` loads previous build |
| Helm release | `helm rollback avengers <N-1>` | < 2 min | `kubectl get pods` all Ready |
| Agent / persona config | `git revert` + admin reload | < 1 min | `GET /tenants/{id}/admin/config/reload` returns updated counts |
| Policy | Same — policies are YAML | < 1 min | `GET /tenants/{id}/agents/{id}` shows new policy list |
| Kill switch (any agent, any tenant) | Admin endpoint sets `tenant.kill_switched[]` | < 30s | Next brief skips that agent, reports in `kill_switched` field |
| Cron secret rotation | `fly secrets set CRON_SECRET=$(openssl rand -hex 32)` + Vercel env | < 2 min | Next cron run succeeds with new secret |

### 10.3 Failure-mode catalog (and recovery)

| Failure | Symptom | Recovery |
|---------|---------|----------|
| LLM provider outage | All `agent.status.error` | Router falls back to `model.fallback` spec automatically; if both down, brief degrades to error sections |
| Connector flake | One section error | Director best-effort; brief ships with that section's error noted |
| Postgres down | API returns 503 | ECS healthcheck fails → ALB drains; Aurora failover ≤ 30s |
| Redis down | Budget hits in-memory fallback (per-replica counter; risk: 2× counted spend during outage) | Acceptable; recovers when Redis returns |
| Region outage | Total outage for region's tenants | Manual failover to secondary region (DR config required; Phase 4) |
| Hostile prompt injection | Eval score drops | CI catches on PR; revert + investigate; mitigate via new policy |
| Audit S3 outage | Audit emits buffered to disk, retried | If outage > 1h, alert security; events queue in memory |
| Memory loss after restart | Each pod restart loses in-memory state (current production gap) | Phase 2 fix: Postgres-back the approval queue + budget counter |

---

## 11. Cost model

### 11.1 Today (running on free tiers)

| Item | Monthly | Notes |
|------|---------|-------|
| Render free | $0 | 512 MB, 750 hrs/month, idle-sleeps |
| Vercel Hobby | $0 | 100 GB bandwidth, serverless function execution |
| Browser STT / TTS | $0 | Web Speech API |
| LLM (DemoLLMProvider stub) | $0 | No real calls |
| Domain | $0 | Using vercel.app subdomain |
| **Total** | **$0** | |

### 11.2 At 100 active users / 10 tenants (post-key)

| Item | Monthly |
|------|---------|
| Render Starter (always-warm) | $7 |
| Vercel Pro (1 seat) | $20 |
| Anthropic Sonnet @ 1k briefs/day × 6k tokens avg | $400 |
| S3 audit (10 GB) | $0.30 |
| **Total** | **~$430** |

### 11.3 At 1k tenants, 10k briefs/day (GA)

| Item | Monthly |
|------|---------|
| ECS Fargate (10 tasks avg, HPA-scaled) | $250 |
| Aurora Serverless v2 (2-8 ACU avg) | $200 |
| Redis ElastiCache t4g.small | $25 |
| S3 audit (500 GB hot, 5 TB Glacier) | $50 |
| KMS (1k CMKs) | $1000 |
| Bedrock Sonnet @ 10k briefs/day × 6k tokens | $4000 |
| CloudWatch + observability | $100 |
| Temporal Cloud (medium) | $500 |
| Vercel Pro (10 seats) | $200 |
| **Total** | **~$6.3k** |

Per-tenant cost ≈ ₹500/month at GA scale. Pricing model in the BRD (₹2,500/store flat OR ₹15/brief metered) gives ~5× gross margin.

### 11.4 Cost discipline mechanisms

- **Per-tenant + per-user daily USD cap** — hard-enforced before each LLM call. Failed charges don't persist (no half-billed state).
- **Per-agent `wallclock_seconds`** — bounds the wall-clock cost of a runaway loop.
- **Per-call `max_tokens_out`** in agent YAML — caps the LLM output spend.
- **Connector caching** (`caching.ttl_seconds` in connector YAML) — same query in 5 min returns cached result, $0 spend.
- **Fallback provider** spec is cheaper than primary; the LLM router falls back automatically on retryable error.

---

## 12. Open items / phase-3 targets

These are deferred from the current build and tracked here so nothing falls through the cracks.

### 12.1 Critical-path (before production)

| Item | Why | Estimated effort |
|------|-----|------------------|
| Real `AnthropicProvider` wired up in `__main__.py` (currently `DemoLLMProvider`) | Brief returns "Demo claim" stub today | 10 min |
| Postgres-backed `briefs`, `approvals`, `users`, `audit_events` | In-memory state lost on restart | 1 week |
| Redis-backed `BudgetTracker` | Per-replica state at scale | 2 days |
| Local JWT verification (PyJWT + JWKS) replacing userinfo round-trip | Per-request IdP round-trip is slow | 1 day |
| S3 audit sink production binding | Object Lock guarantee | 1 day |
| KMS per-tenant key on the Audit S3 sink | Compliance | 0.5 day |
| ≥ 20 eval cases per agent (today: 3 for research) | GA quality gate | 1 week |
| Slack + Teams + SES email delivery adapters | "Brief at 7 a.m. in Slack" | 1 week |
| SAML adapter (OIDC done) | Enterprise customers | 3 days |

### 12.2 Quality of life (next-quarter)

| Item | Why |
|------|-----|
| Better STT — OpenAI Whisper API in `jarvis-desktop` instead of Google free | Higher accuracy en-IN, better negation handling |
| TTS upgrade to ElevenLabs voice | More natural "Cap Brij" persona voice |
| Per-tenant DR with cross-region S3 replication | RPO ≤ 0 across regions |
| Audit-search UI in dashboard | Today the audit is queryable only by direct S3 / Postgres access |
| Cost dashboard in `/admin` | Today exposed via API only |
| Mobile-native dashboard wrapper | PWA already works; native gives push notif + better mic on iOS |
| Web Speech alternative for Firefox | Falls back to text-only today |

### 12.3 Strategic (year-1)

| Item | Why |
|------|-----|
| Agent Extension marketplace (BRD §9.3) | Two-sided platform play |
| Real Fynd / JioCommerce live connector (replacing stubs) | True merchant value |
| Multi-region deploy in `us-east-1` + `eu-west-1` | Latency for non-IN tenants |
| FedRAMP / SOC 2 Type II evidence collection | Enterprise procurement |
| BYO-model (let tenants bring their own LLM key) | Cost-of-goods control |

---

## Appendix A — file map

```
avengers-jarvis1/
├── README.md            ← quickstart + deploy buttons
├── SPEC.md              ← original engineering mandate
├── BRD.md               ← business case
├── CAPABILITIES.md      ← flat lookup catalog
├── RELEASE_PLAN.md      ← phased delivery
├── DEPLOY.md            ← operational runbook
├── SYSTEM_DESIGN.md     ← THIS DOCUMENT
├── package.json         ← root npm shim (Vercel framework detection)
├── pyproject.toml       ← Python project metadata
├── vercel.json          ← Vercel build + cron config
├── render.yaml          ← Render Blueprint
├── fly.toml             ← Fly.io alt deploy
├── api/                 ← (Vercel attempt residue; not active path)
├── config/
│   ├── tenants/         ← acme.yaml, fynd_internal.yaml, jarvis.yaml
│   ├── agents/          ← 9 specialist configs
│   ├── connectors/      ← 5 connector configs
│   └── policies/        ← 3 baseline + 2 Fynd-specific
├── prompts/             ← per-agent system prompts
├── memory/jarvis/       ← Cap Brij persona + reference files
├── src/avengers/
│   ├── schemas/         ← Pydantic v2 models
│   ├── core/            ← tenant ctx, policy, audit, redact, budget, rbac, config loader
│   ├── llm/             ← Protocol + 5 adapters + router
│   ├── memory/          ← Protocol + 5 implementations
│   ├── identity/        ← Protocol + Static + OIDC + SCIM
│   ├── delivery/        ← Protocol + Console (+ 6 shape-ready)
│   ├── connectors/      ← Protocol + 5 active connectors
│   ├── agents/          ← BaseAgent + Director + 9 specialists
│   ├── workflows/       ← morning_brief, deep_dive, approval
│   ├── api/             ← FastAPI app + 19 routes
│   ├── observability/   ← metrics, tracing, langfuse
│   └── evals/           ← harness + scorer registry
├── jarvis-desktop/
│   ├── listener.py      ← Hey JARVIS daemon for macOS
│   ├── com.capbrij.jarvis.plist  ← launchd manifest
│   └── README.md        ← install + autostart
├── web/                 ← Next.js dashboard (11 routes)
├── infra/
│   ├── terraform/       ← 8 modules for AWS deploy
│   ├── helm/            ← Kubernetes chart
│   └── docker/          ← api + worker Dockerfiles
└── tests/               ← 90 pytest cases + 12 Playwright specs
```

---

## Appendix B — environment variables (reference)

### Backend (Render / Fly / Docker)

| Variable | Required? | Default | Purpose |
|----------|-----------|---------|---------|
| `AVENGERS_ENVIRONMENT` | no | `dev` | One of `dev / staging / prod` |
| `AVENGERS_LOG_LEVEL` | no | `INFO` | Standard log levels |
| `AVENGERS_REGION` | no | `us-east-1` | For audit / KMS region pinning |
| `AVENGERS_CORS_ORIGINS` | no | `http://localhost:3000,http://web:3000` | Comma-separated; `https://*.vercel.app` and `null` (for desktop helper) supported |
| `AVENGERS_CONFIG_DIR` | no | `config` | YAML config location |
| `AVENGERS_PROMPTS_DIR` | no | `prompts` | Prompt files location |
| `COMMERCE_BACKEND` | no | `fynd` | One of `fynd / jio / both` |
| `CRON_SECRET` | for cron | (none) | Shared secret for Vercel Cron → backend |
| `ANTHROPIC_API_KEY` | for real LLM | (none) | When swapping `DemoLLMProvider` for `AnthropicProvider` |
| `DATABASE_URL` | for prod | (none) | Postgres connection string when wired |
| `REDIS_URL` | for prod | (none) | Redis for budget + approvals |
| `AUDIT_S3_BUCKET` | for prod audit | (none) | Per-tenant bucket name pattern |
| `AUDIT_KMS_KEY_ARN` | for prod audit | (none) | Per-tenant CMK |

### Frontend (Vercel)

| Variable | Required? | Purpose |
|----------|-----------|---------|
| `AVENGERS_API_INTERNAL` | yes | Backend URL — what `next.config.mjs` rewrites `/api/avengers/*` to |
| `CRON_SECRET` | yes | Match the backend's value; Vercel Cron route forwards as `X-Cron-Secret` |
| `JARVIS_TENANT` | no | Default tenant for the cron handler (default `jarvis`) |

### Desktop helper

| Variable | Required? | Purpose |
|----------|-----------|---------|
| `JARVIS_API_BASE` | yes | Backend URL (Render direct OR Vercel proxy) |
| `JARVIS_API_PATH_PREFIX` | no | Empty for Render direct; `/api/avengers` for Vercel proxy |
| `JARVIS_TOKEN` | yes | Bearer token (`user:cap-brij` in dev, real OIDC token in prod) |
| `JARVIS_TENANT` | no | Defaults to `jarvis` |
| `JARVIS_QUERY_SECS` | no | Defaults to 8 |
| `JARVIS_LOG_LEVEL` | no | Defaults to `INFO` |

---

## Appendix C — runbook for common operations

### Onboard a new tenant

1. Drop `config/tenants/<id>.yaml` with their identity provider, budget, region.
2. Drop `config/agents/<id>.yaml` for any new custom agents (optional).
3. Drop `memory/<id>/persona.md` if they want a custom persona.
4. POST `/tenants/<id>/admin/config/reload` (admin token).
5. Provision per-tenant KMS key + audit bucket via Terraform (`module.kms`, `module.s3-audit`).
6. Set up SCIM endpoint at the tenant's IdP.
7. First user logs in → OIDC roundtrip succeeds → `/healthz` shows tenant counted.

### Add a new specialist agent

1. Pydantic digest in `src/avengers/schemas/brief.py` (`<Name>Digest`).
2. 4-line `BaseAgent[<Digest>]` subclass in `src/avengers/agents/<name>.py`.
3. Register in `bootstrap._SPECIALIST_CLASSES`.
4. YAML in `config/agents/<name>.yaml`.
5. Prompt in `prompts/<name>.md`.
6. Add agent ID to the tenant's `agents_enabled` list.
7. Drop ≥ 20 eval cases under `evals/cases/<name>/`.
8. Hot reload via admin endpoint. New brief includes the new section.

### Rotate the cron secret

```bash
NEW=$(openssl rand -hex 32)
# Backend (Render):
fly secrets set CRON_SECRET=$NEW            # or render dashboard
# Frontend (Vercel):
vercel env rm CRON_SECRET production
vercel env add CRON_SECRET                  # paste $NEW
# Trigger a redeploy on both sides
```

### Hot-reload YAML config without restart

```bash
curl -X POST https://<api>/tenants/<tenant>/admin/config/reload \
  -H "Authorization: Bearer <admin-token>"
# Returns: {"ok": true, "tenants": N, "agents": M, "policies": K}
```

### Kill-switch an agent for a tenant

Edit the tenant's YAML, add agent ID to `kill_switched: [...]`, reload config. Next brief skips that agent and records it in `MorningBrief.kill_switched`.

### Replay a brief

Briefs are immutable. Re-run with the same `for_date` creates a new row. The original stays for audit.

```bash
curl -X POST https://<api>/tenants/<id>/briefs \
  -H "Authorization: Bearer <token>" \
  -d '{"for_date": "2026-05-17"}'
```

---

**Document version:** 1.0
**Generated for:** Cap Brij
**Source of truth:** this file. If anything in the running system disagrees with this document, fix the system or fix the document — never let them drift.

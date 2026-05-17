# AVENGERS Platform — Release Plan (SPEC §15)

This is the operational rollout plan for v1.0 GA. Phases are sequential; each
gate is binary — no phase begins until the previous phase's exit criteria are
all green.

## Phase 0 — Foundation (weeks 1–2) — **complete in this branch**

Goal: skeleton that an engineer can stand up locally in under 10 minutes.

| Exit criterion                                        | Status         |
| ----------------------------------------------------- | -------------- |
| Repo layout per SPEC §6                               | ✅ done         |
| Pydantic schemas for every domain object              | ✅ done         |
| YAML config loader with hot reload                    | ✅ done         |
| PII redactor with ordered patterns                    | ✅ done         |
| ≥ 40 unit tests passing                               | ✅ 79 passing   |

## Phase 1 — Interfaces + reference agents (weeks 3–4)

Goal: every external surface lives behind a Protocol; one specialist runs
end-to-end against fakes; first sample tenant boots.

| Exit criterion                                                        | Status |
| --------------------------------------------------------------------- | ------ |
| LLM / Memory / Identity / Delivery / Connector / Policy interfaces    | ✅      |
| Anthropic + Fake LLM providers                                        | ✅      |
| In-memory + FS memory stores                                          | ✅      |
| Director + 6 specialist classes (digest schemas typed)                | ✅      |
| Approval queue with await/decide/timeout                              | ✅      |
| Sample ACME tenant + research agent + 3 policies load                 | ✅      |

## Phase 2 — Control plane + security (weeks 5–7)

Goal: customer can call the API with an OIDC token, trigger a brief, and the
audit trail is immutable.

| Exit criterion                                                | Status              |
| ------------------------------------------------------------- | ------------------- |
| FastAPI control plane with bearer auth + cross-tenant 403     | ✅                   |
| OIDC adapter (userinfo flow) with caching                     | ✅                   |
| SCIM 2.0 ingress (admin-gated)                                | ✅                   |
| S3 audit sink with COMPLIANCE Object Lock + SSE-KMS           | ✅                   |
| Local JWT verification (PyJWT + JWKS) replaces userinfo       | TODO — Phase 3      |
| Postgres-backed brief + audit shadow read                     | TODO — Phase 3      |
| Penetration test on staging                                   | TODO — Phase 4      |

## Phase 3 — Observability + cost discipline (weeks 8–9)

Goal: every model call has a price tag; every brief has a trace; a budget
breach is impossible.

| Exit criterion                                                | Status |
| ------------------------------------------------------------- | ------ |
| Per-call metrics (cost, tokens, latency) fired into Prometheus | ✅      |
| Span tracing of every LLM + tool call                          | ✅      |
| Langfuse-shaped trace sink                                     | ✅      |
| Eval harness with closed scorer registry + gate-score check    | ✅      |
| ≥ 20 eval cases per agent                                      | TODO   |
| Grafana dashboards: cost/user, latency p95/p99, error rate     | TODO   |
| Cost-cap alerting at 80% of daily cap                          | TODO   |

## Phase 4 — Deployment + SRE (weeks 10–11)

Goal: one Terraform apply spins up an isolated tenant in any region.

| Exit criterion                                                  | Status |
| --------------------------------------------------------------- | ------ |
| Terraform modules: vpc, kms, secrets, s3-audit, aurora, ecs, bedrock, temporal | ✅      |
| Per-tenant KMS + audit bucket + secret namespace                 | ✅      |
| Helm chart (api + worker deployments, HPA, NetworkPolicy)        | ✅      |
| Dockerfile.api + Dockerfile.worker (non-root, read-only fs)      | ✅      |
| docker-compose.dev.yml: api + web + postgres + temporal          | ✅      |
| Runbook: tenant onboarding in < 1h                               | TODO   |
| Disaster-recovery drill (region failover)                        | TODO   |

## Phase 5 — Dashboard + delivery channels (weeks 12–13)

Goal: a user opens the dashboard at 7 a.m. and reads their brief.

| Exit criterion                                                  | Status |
| --------------------------------------------------------------- | ------ |
| Next.js dashboard: Today / Agents / Approvals / Audit            | ✅      |
| Real-time SSE for brief progress                                 | ✅      |
| Slack + Teams adapters (Block Kit / Adaptive Cards)              | TODO   |
| SES email adapter with HTML rendering                            | TODO   |
| Quiet-hours enforcement + per-channel preferences                | TODO   |

## Phase 6 — Hardening (weeks 14–15)

| Gate                              | Owner       |
| --------------------------------- | ----------- |
| Pentest passed                    | Security    |
| SOC 2 Type II controls evidenced  | Compliance  |
| DPIA signed off                   | Compliance  |
| Cost regression vs. baseline ≤ 5% | Platform    |
| p95 brief latency ≤ 90s @ 100 RPS | Platform    |
| Chaos test: connector outage → graceful degrade | SRE |

## GA criteria

All of:

1. Phases 0–6 gates green.
2. Two internal beta tenants live for ≥ 4 weeks with zero data-loss incidents.
3. Daily cost variance < 10% week-over-week for one full month.
4. Brief faithfulness eval ≥ 0.90 averaged across all six specialists.
5. Mean time-to-mitigate prompt-injection regressions ≤ 24h.
6. Customer-facing docs + admin runbook published.

## Rollout strategy

- **Internal alpha** (T-6 weeks): one tenant (internal), one workspace.
- **Closed beta** (T-3 weeks): 5 design-partner tenants, no public sign-up.
- **Open beta** (T-1 week): self-serve onboarding behind a feature flag with
  per-tenant daily cap of $50 hard-locked.
- **GA** (T+0): remove flag, raise default cap to $250, publish status page.

## Rollback

Each phase's rollback steps live next to its runbook in `infra/runbooks/`.
Critical-path rollbacks:

| Surface              | Rollback                                          | Time   |
| -------------------- | ------------------------------------------------- | ------ |
| API task definition  | `aws ecs update-service --task-definition <prev>` | < 2min |
| Helm release         | `helm rollback avengers <N-1>`                    | < 2min |
| Agent config         | `git revert` + admin reload                       | < 1min |
| Policy change        | same — policies are YAML                          | < 1min |
| Kill switch          | admin endpoint flips the kill_switched list       | < 30s  |

## Open risks

1. **Cost spikes from runaway tool loops.** Mitigated by per-agent
   `wallclock_seconds` + per-tenant daily cap + per-user cap; need
   throttle-back on connector retries.
2. **Prompt injection from external content.** Mitigated by `cite_every_claim`
   + redaction; need a curated jailbreak eval set per release.
3. **Connector flakiness during morning peak.** Mitigated by best-effort
   section status; need per-connector circuit breakers.
4. **JWT verification round-trip cost.** Mitigated short-term by per-token
   cache; long-term swap to local JWT validation with JWKS.

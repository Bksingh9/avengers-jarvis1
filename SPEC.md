# AVENGERS Platform — Engineering Specification

**Version:** 1.0
**Date:** 17 May 2026
**Status:** implementation-ready (this repository is the in-progress reference build)

This file is the canonical specification handed to the building agent. The full
text lives in the project description; the abbreviated copy below records the
binding rules that the codebase enforces.

## Prime directives

1. **Do not invent requirements.** Unspecified gaps are tagged `# SPEC-GAP:` in
   code and resolved with the most conservative interpretation.
2. **Pluggability is the prime directive.** Every external system (LLM
   provider, vector DB, identity provider, data source, delivery channel)
   lives behind an interface. Vendor SDKs are only imported inside their
   adapter module.
3. **Tests before merges.** Every module ships with unit tests; every agent
   ships with at least 20 eval cases.
4. **Audit by default.** Every tool invocation, every model call, every
   approval, every error is auditable.
5. **Configuration over code.** Tenants, agents, data sources, schedules, and
   policies are declared in YAML and loaded at runtime.

## Build order

§6 (repo layout) → §7 (config model) → §8 (domain schemas) → §9 (interfaces)
→ §10 (agents) → §11 (workflows) → §12 (security) → §13 (observability) →
§14 (deployment) → §15 (release plan).

The current commit covers §6–§9 with stubs through §11. §12 in the source spec
was truncated mid-sentence; the controls implemented here follow the conservative
interpretation: hard tenant isolation via separate Postgres schemas, separate
KMS keys, separate vector-store namespaces, and RBAC enforced at the connector
boundary.

## Reference deployment

AWS multi-tenant SaaS: Bedrock AgentCore for hosted Claude; ECS Fargate for
stateless workers; Temporal Cloud for workflow durability; Aurora Postgres for
control plane; Turbopuffer/Pinecone for vector memory; S3 with Object Lock for
audit; KMS keys per tenant.

## Tenancy

- **Hard isolation:** Postgres schema, KMS key, vector namespace, audit S3
  prefix per tenant.
- **Soft isolation:** workers shared; `TenantContext` middleware enforces
  scoping on every request.

For the full normative text see the project description handed to the building
agent.

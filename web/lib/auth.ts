/**
 * Dev-mode bearer token. The seeded FastAPI `__main__` accepts `user:<id>`
 * tokens via the StaticIdentityProvider. Swap for a real OIDC redirect flow
 * before GA.
 */
export const DEMO_TOKEN = "user:alice";
export const DEMO_TENANT = "acme";

export function authHeaders(): HeadersInit {
  return { Authorization: `Bearer ${DEMO_TOKEN}` };
}

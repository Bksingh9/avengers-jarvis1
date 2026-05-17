# AVENGERS Dashboard

Next.js 14 (App Router) · React 18 · Tailwind · framer-motion · cmdk · SWR · Sonner.

## What you get

- **Today** — morning brief that streams in section-by-section via SSE.
  Glassmorphism cards animate as each specialist finishes; cost ticker fills
  proportional to your daily cap; auto-runs on mount.
- **Agents** — registry of the six specialists with model + policy badges.
- **Approvals** — live human-in-the-loop queue with approve/deny actions and
  5-second auto-refresh.
- **Audit** — placeholder for the S3 audit live-tail.
- **Settings** — identity, tenant, delivery preferences.
- **Command palette (⌘K)** — navigate, trigger a brief, jump to today.

## Run it (with the FastAPI backend)

In one terminal:

```bash
cd avengers
uvicorn avengers.api.__main__:app --port 8080
```

In another:

```bash
cd avengers/web
npm install
npm run dev
# open http://localhost:3000
```

## Or with docker-compose (api + web + postgres + temporal)

```bash
cd avengers
docker compose -f docker-compose.dev.yml up --build
```

## Auth

Uses a dev bearer token `user:alice` accepted by the seeded
`StaticIdentityProvider` in `avengers/api/__main__.py`. Swap for an OIDC
redirect flow (NextAuth or @auth/nextjs) before any non-dev deployment.

## Architecture

- All API calls go through `lib/api.ts` — single typed surface.
- `next.config.mjs` rewrites `/api/avengers/*` to the FastAPI base URL so the
  browser never hits the backend directly (CORS-safe, easier to swap origins).
- SSE consumed manually (`streamBrief`) so the cleanup function can abort the
  underlying fetch on unmount.
- Theme is CSS-variable-driven (HSL triples) — flip the `dark` class on `<html>`
  to toggle. Currently dark-by-default.

## Why these libraries

- **framer-motion** — entrance/exit animations on streaming section cards.
- **cmdk** — command palette UX matches the rest of the design system.
- **SWR** — soft cache + revalidate-on-focus for the registry pages.
- **sonner** — non-blocking toasts for stream events and approval decisions.
- **lucide-react** — icon set with stable filesize and good a11y defaults.

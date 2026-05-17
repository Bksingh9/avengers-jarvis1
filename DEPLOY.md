# Deploying AVENGERS — Vercel (web) + Fly.io (backend)

This is the "10-minute demo deploy" path. It pairs Vercel for the Next.js
dashboard with Fly.io for the FastAPI control plane — Vercel's serverless
runtime doesn't play well with our SSE-based brief stream, but Fly's tiny
always-on machines do, and Fly's `bom` (Mumbai) region is closest for Fynd.

## Prereqs

- A GitHub account with this repo pushed (the `claude/build-avengers-platform-poDQP` branch).
- A free Vercel account.
- A Fly.io account + `flyctl` CLI: `curl -L https://fly.io/install.sh | sh`.

## Step 1 — deploy the backend to Fly.io

```bash
cd avengers
fly auth login
fly launch --copy-config --no-deploy   # adopt the shipped fly.toml
# Pick a unique app name if `avengers-api` is taken; note it down.
fly deploy
fly status
fly logs                                # confirm "Uvicorn running on..."
```

Take the hostname (`https://<your-app>.fly.dev`) — you'll paste it into
Vercel next.

Smoke test:

```bash
curl https://<your-app>.fly.dev/healthz
# {"status":"ok","tenants":2,"agents":9,"connectors_known":[...]}
```

## Step 2 — deploy the web app to Vercel

### Option A — one-click via the UI

1. Vercel → **Add New → Project → Import Git Repository** → pick this repo.
2. **Root Directory:** `avengers/web` (critical — Vercel needs to point at the
   web sub-folder, not the repo root).
3. Framework Preset: **Next.js** (auto-detected).
4. **Environment Variables:**
   - `AVENGERS_API_INTERNAL` = `https://<your-app>.fly.dev`
5. Click **Deploy**.

### Option B — Vercel CLI

```bash
cd avengers/web
npx vercel
# When prompted, set the root to ".", framework to next, and add the env var
npx vercel env add AVENGERS_API_INTERNAL  # paste https://<your-app>.fly.dev
npx vercel --prod
```

Open the resulting `https://<project>.vercel.app/dashboard` — the brief
streams in immediately.

## Step 3 — wire CORS for the new Vercel origin

The Fly env already allows `https://*.vercel.app` (set in `fly.toml`), so
preview deployments work out of the box. If you put the app on a custom
domain:

```bash
fly secrets set AVENGERS_CORS_ORIGINS="https://app.your-domain.com,https://*.vercel.app,http://localhost:3000"
```

## Step 4 — Playwright e2e against the live deployment

```bash
cd avengers/web
npm install
npm run test:e2e:install         # one-time chromium download
PLAYWRIGHT_BASE_URL=https://<your-project>.vercel.app npm run test:e2e
```

Three specs run:

| Spec               | Checks                                                        |
| ------------------ | ------------------------------------------------------------- |
| `dashboard.spec`   | Hero renders; brief streams; ⌘K opens the command palette.   |
| `agents.spec`      | Agents page lists at least one specialist.                    |
| `approvals.spec`   | Approvals page renders.                                       |

## To see the Fynd tenant after deploy

Vercel can hold two sets of env vars per environment (preview vs. production).
Two ways to flip the dashboard to the Fynd tenant:

**Quick (dev only)** — edit `web/lib/auth.ts`, set `DEMO_TOKEN = "user:fynd-alice"`
and `DEMO_TENANT = "fynd_internal"`, redeploy.

**Production** — replace `lib/auth.ts` with a real OIDC integration
(NextAuth or `@auth/nextjs`) wired to the IdP set in `fly secrets` as
`AVENGERS_OIDC_ISSUER`.

## Rollback

| Surface         | How                                          | Time     |
| --------------- | -------------------------------------------- | -------- |
| Backend (Fly)   | `fly releases` then `fly releases rollback`  | < 30s    |
| Web (Vercel)    | Vercel UI → Deployments → previous → Promote | < 1 min  |

## Cost (Nov 2026)

- **Fly.io free tier:** 3 shared-cpu-1x VMs / 256 MB free; the AVENGERS API
  fits 2 of those if you scale to a single replica. Bumping to a 1 GB machine
  is ~$2/month per instance.
- **Vercel Hobby plan:** free for the dashboard; no quota concerns for a
  demo / internal pilot.
- **LLM cost:** zero today — the seeded `__main__` uses the schema-
  introspecting `DemoLLMProvider`. Swap to real Anthropic / Bedrock by
  registering the provider in `__main__._build()` and setting `ANTHROPIC_API_KEY`
  via `fly secrets set`.

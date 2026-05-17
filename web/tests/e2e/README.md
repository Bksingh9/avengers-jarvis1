# Playwright e2e tests

Three specs exercise the running dashboard end-to-end against the FastAPI
control plane.

## Run locally

```bash
# 1) Backend (separate terminal)
cd ../..               # → avengers/
PYTHONPATH=src uvicorn avengers.api.__main__:app --port 8080

# 2) Tests (this terminal)
cd avengers/web
npm install
npm run test:e2e:install   # one-time: download chromium
npm run test:e2e           # headless
npm run test:e2e:ui        # interactive (great for debugging)
```

Playwright will auto-start `next dev` on port 3000 via the `webServer`
config — you don't need to run it manually.

## Run against a deployed environment

```bash
PLAYWRIGHT_BASE_URL=https://your-app.vercel.app npm run test:e2e
```

The `webServer` step is skipped automatically when `PLAYWRIGHT_BASE_URL`
is set.

## Specs

| File                 | What it checks                                          |
| -------------------- | ------------------------------------------------------- |
| `dashboard.spec.ts`  | Hero renders; brief streams to at least one section card; ⌘K opens the command palette. |
| `agents.spec.ts`     | Agents page lists at least one known specialist.        |
| `approvals.spec.ts`  | Approvals page renders either empty-state or a row.     |

Add new specs as you ship features. Keep selectors role-based
(`getByRole`, `getByText`) so tests survive cosmetic refactors.

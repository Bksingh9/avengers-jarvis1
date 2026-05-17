"""Vercel Python serverless catch-all → mounts the full FastAPI app.

How Vercel routes here:
  Request:  GET  https://<project>.vercel.app/api/avengers/healthz
  Vercel rewrite (in vercel.json): /api/avengers/:path*  →  /api/:path*
  Match against this file:         /api/healthz  →  api/[[...path]].py
  Mangum unwraps the AWS-Lambda-style event into ASGI for FastAPI
  FastAPI handles /healthz as if it were running locally.

Cold-start budget on Vercel Hobby:
  * 3-5 s on first invocation (config load + connector registry)
  * <100 ms on warm invocations
  * 60 s max duration (enough for streaming briefs in demo mode)

The function bundle includes src/, config/, prompts/, memory/ via
includeFiles in vercel.json.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))
os.environ.setdefault("AVENGERS_CONFIG_DIR", str(_ROOT / "config"))
os.environ.setdefault("AVENGERS_PROMPTS_DIR", str(_ROOT / "prompts"))

# Default the CORS allow-list so the dashboard (same Vercel project) plus any
# preview URL can talk to the backend. Override via Vercel env vars.
os.environ.setdefault("AVENGERS_CORS_ORIGINS", "https://*.vercel.app,http://localhost:3000")
os.environ.setdefault("COMMERCE_BACKEND", "both")

# Lazy-import after the path + env setup above is in place.
from mangum import Mangum  # noqa: E402

from avengers.api.__main__ import app  # noqa: E402

# `api_gateway_base_path` strips the /api prefix Vercel sees before handing
# the request to FastAPI, so FastAPI matches routes as if it were running
# bare on port 8080 (e.g. `/healthz`, `/tenants/jarvis/agents`).
handler = Mangum(app, lifespan="off", api_gateway_base_path="/api")

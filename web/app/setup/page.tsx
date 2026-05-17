"use client";

import { motion } from "framer-motion";
import { Check, Circle, Copy } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

interface Step {
  id: string;
  title: string;
  description: string;
  commands?: string[];
  what: string;
  verify?: string;
}

const STEPS: Step[] = [
  {
    id: "clone",
    title: "Clone the repo",
    description: "Pull the AVENGERS + JARVIS branch onto your machine.",
    commands: [
      "git clone https://github.com/Bksingh9/thrive-record-hub.git",
      "cd thrive-record-hub",
      "git checkout claude/build-avengers-platform-poDQP",
    ],
    what:
      "You get the full backend, the dashboard, the JARVIS persona files, the 9 specialists, and the Fynd / Jio adapters — about 18k lines, 90 tests.",
  },
  {
    id: "py-deps",
    title: "Install backend deps",
    description: "Python 3.11+ (your anaconda 3.12 is fine).",
    commands: [
      "cd avengers",
      "pip install fastapi 'pydantic[email]' pydantic-settings pyyaml httpx uvicorn pytest pytest-asyncio",
    ],
    what:
      "These are the runtime essentials. Heavier extras (boto3, asyncpg, opentelemetry) are optional — install via `pip install -e \".[dev]\"` when you want them.",
    verify: "python3 -m pytest tests -q",
  },
  {
    id: "boot-backend",
    title: "Boot the backend",
    description: "uvicorn on port 8080. Leave this terminal running.",
    commands: ["PYTHONPATH=src uvicorn avengers.api.__main__:app --port 8080"],
    what:
      "Spins up the FastAPI control plane with 3 seeded tenants (acme, fynd_internal, jarvis), 9 specialists, and the DemoLLMProvider so no API key is needed for the first run.",
    verify: "curl -s http://localhost:8080/healthz",
  },
  {
    id: "boot-web",
    title: "Boot the dashboard",
    description: "New terminal. Next.js on port 3000.",
    commands: ["cd avengers/web", "npm install", "npm run dev"],
    what:
      "Glassmorphism dashboard with the brief streaming via SSE. Open http://localhost:3000 — it auto-runs the brief on mount.",
  },
  {
    id: "switch-jarvis",
    title: "Switch to the JARVIS tenant",
    description: "Edit web/lib/auth.ts to log in as Cap Brij.",
    commands: [
      "// in web/lib/auth.ts",
      "export const DEMO_TOKEN = \"user:cap-brij\";",
      "export const DEMO_TENANT = \"jarvis\";",
    ],
    what:
      "Save and the dashboard hot-reloads. Visit /jarvis for the conversational page with the voice orb. The persona is active — JARVIS addresses you as Cap Brij.",
  },
  {
    id: "commerce-backend",
    title: "Pick your commerce backend",
    description: "Fynd Platform, JioCommerce, or both.",
    commands: [
      "# Restart the backend with one of:",
      "COMMERCE_BACKEND=fynd  PYTHONPATH=src uvicorn avengers.api.__main__:app --port 8080  # default",
      "COMMERCE_BACKEND=jio   PYTHONPATH=src uvicorn avengers.api.__main__:app --port 8080",
      "COMMERCE_BACKEND=both  PYTHONPATH=src uvicorn avengers.api.__main__:app --port 8080",
    ],
    what:
      "Same tool names (list_orders, fulfillment_health, …) work against either platform. Wire real credentials by setting JIOCOMMERCE_BASE_URL / JIOCOMMERCE_COMPANY_ID and FYND_API_KEY / FYND_API_SECRET in your shell or .env.",
  },
  {
    id: "deploy",
    title: "Deploy live",
    description: "Backend → Fly.io (Mumbai). Web → Vercel.",
    commands: [
      "curl -L https://fly.io/install.sh | sh",
      "fly auth login",
      "fly launch --copy-config --no-deploy   # adopt the shipped fly.toml",
      "fly deploy",
      "fly secrets set CRON_SECRET=$(openssl rand -hex 32)",
      "# Then on Vercel: Add New → Project → Root Directory: avengers/web",
      "# Env var: AVENGERS_API_INTERNAL = https://<your-app>.fly.dev",
    ],
    what:
      "Fly hosts the FastAPI control plane (SSE-friendly, 1 GB Mumbai machine, $0 free tier). Vercel hosts the dashboard. Vercel Cron pings /jarvis/proactive every morning using the CRON_SECRET you set.",
  },
  {
    id: "voice",
    title: "Talk to JARVIS",
    description: "Open the dashboard, click the orb, hold to speak.",
    commands: ["# open https://<your-project>.vercel.app/jarvis"],
    what:
      "Uses your browser's native Web Speech API — no extra keys. Hold the orb to record (en-IN locale), release to send. JARVIS thinks, then replies in voice + text with citation chips for every claim.",
  },
];

export default function SetupPage() {
  const [done, setDone] = useState<Set<string>>(new Set());

  const toggle = (id: string) =>
    setDone((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const pct = Math.round((done.size / STEPS.length) * 100);

  return (
    <div className="space-y-6">
      <header>
        <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Get started</p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight">
          JARVIS in 8 steps.
        </h1>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
          Each step is copy-paste-ready. Tick as you go — your progress lives in
          this browser tab. Backend deploys to Fly, dashboard to Vercel, voice
          runs in your browser.
        </p>
      </header>

      <div className="glass flex items-center gap-4 rounded-2xl p-4">
        <div className="num text-2xl font-semibold">{pct}%</div>
        <div className="flex-1">
          <div className="h-2 overflow-hidden rounded-full bg-muted/40">
            <motion.div
              className="h-full bg-gradient-to-r from-primary to-accent"
              initial={{ width: 0 }}
              animate={{ width: `${pct}%` }}
              transition={{ duration: 0.4 }}
            />
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {done.size} of {STEPS.length} steps complete
          </p>
        </div>
      </div>

      <div className="space-y-4">
        {STEPS.map((step, i) => {
          const isDone = done.has(step.id);
          return (
            <Card key={step.id} className={cn("transition-all", isDone && "border-success/50")}>
              <CardHeader>
                <div className="flex items-start justify-between gap-3">
                  <button
                    type="button"
                    onClick={() => toggle(step.id)}
                    className={cn(
                      "mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full border-2 transition-colors",
                      isDone
                        ? "border-success bg-success text-background"
                        : "border-border text-muted-foreground hover:border-primary",
                    )}
                    aria-label={isDone ? "Mark incomplete" : "Mark complete"}
                  >
                    {isDone ? <Check size={12} /> : <Circle size={10} />}
                  </button>
                  <div className="flex-1">
                    <CardTitle className="flex items-center gap-2 text-base">
                      <span className="num text-muted-foreground">{i + 1}.</span>
                      {step.title}
                    </CardTitle>
                    <p className="mt-1 text-sm text-muted-foreground">{step.description}</p>
                  </div>
                  <Badge tone={isDone ? "success" : "default"}>{isDone ? "done" : "todo"}</Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                {step.commands && <CodeBlock lines={step.commands} />}
                <p className="text-xs text-muted-foreground">{step.what}</p>
                {step.verify && (
                  <div className="rounded-md border border-border/60 bg-muted/30 p-2 text-xs">
                    <span className="font-semibold text-foreground">Verify: </span>
                    <code className="num">{step.verify}</code>
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Once everything is green</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          <ul className="space-y-2">
            <li>• Set <code className="num text-foreground">CRON_SECRET</code> on Fly and add the matching Vercel Cron in <code>vercel.json</code> so the morning brief auto-pushes at 06:30 IST.</li>
            <li>• Drop your voice samples + people list into <code className="num text-foreground">memory/jarvis/style.md</code> and <code className="num text-foreground">memory/jarvis/people.md</code> — JARVIS reads them every turn.</li>
            <li>• Wire a Telegram bot via <code>@BotFather</code> and point it at <code className="num text-foreground">POST /tenants/jarvis/jarvis/converse</code> for off-machine voice in/out.</li>
            <li>• Run Playwright against your Vercel URL: <code className="num text-foreground">PLAYWRIGHT_BASE_URL=https://… npm run test:e2e</code>.</li>
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}

function CodeBlock({ lines }: { lines: string[] }) {
  const copy = () => {
    navigator.clipboard.writeText(lines.join("\n"));
    toast.success("Copied");
  };
  return (
    <div className="group relative overflow-hidden rounded-lg border border-border/60 bg-background/40">
      <button
        type="button"
        onClick={copy}
        className="absolute right-2 top-2 rounded-md p-1 text-muted-foreground opacity-0 transition-opacity hover:bg-muted hover:text-foreground group-hover:opacity-100"
        aria-label="Copy"
      >
        <Copy size={12} />
      </button>
      <pre className="overflow-x-auto p-3 text-xs leading-relaxed text-muted-foreground">
        {lines.map((line, i) => (
          <code key={i} className="num block">
            {line.startsWith("#") || line.startsWith("//") ? (
              <span className="text-muted-foreground/60">{line}</span>
            ) : (
              <span>
                <span className="text-success/70">$</span> <span className="text-foreground">{line}</span>
              </span>
            )}
          </code>
        ))}
      </pre>
    </div>
  );
}

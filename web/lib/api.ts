/**
 * Typed client for the FastAPI control plane. Single point of contact with
 * the backend; UI components import from here, never `fetch` directly.
 *
 * Calls go through `/api/avengers/*` which `next.config.mjs` rewrites to the
 * real API base URL (`http://api:8080` in Docker, `http://localhost:8080`
 * in dev).
 */
import { DEMO_TENANT, authHeaders } from "@/lib/auth";

const API_BASE =
  typeof window === "undefined"
    ? process.env.AVENGERS_API_INTERNAL ?? "http://localhost:8080"
    : "/api/avengers";

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { ...authHeaders(), "Content-Type": "application/json", ...(init.headers ?? {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status} ${path}: ${text}`);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

// ----- types ---------------------------------------------------------------

export interface Tenant {
  id: string;
  name: string;
  region: string;
  timezone: string;
  agents_enabled: string[];
  budgets: { daily_usd_cap: number; per_user_usd_cap: number };
}

export interface Me {
  id: string;
  email: string;
  display_name: string;
  tenant_id: string;
  groups: string[];
  timezone: string;
  delivery_prefs: { channels: string[]; morning_time_local: string };
}

export interface AgentSummary {
  id: string;
  display_name: string;
  version: string;
  model: string;
  policies: string[];
}

export interface Source {
  connector: string;
  tool: string;
  ref: string;
  ts: string;
}

export interface Cited {
  text: string;
  sources: Source[];
  confidence: number;
}

export interface BriefSection {
  agent: string;
  status: "ok" | "partial" | "skipped" | "error";
  digest: Record<string, Cited[] | unknown>;
  latency_ms: number;
  cost_usd: number;
  error?: string | null;
}

export interface ApprovalRequest {
  id: string;
  tenant_id: string;
  requested_by_agent: string;
  requested_for_user: string;
  action: string;
  payload: Record<string, unknown>;
  status: "pending" | "approved" | "denied" | "expired";
  created_at: string;
}

// ----- calls --------------------------------------------------------------

export const api = {
  health: () => call<{ status: string; tenants: number; agents: number; connectors_known: string[] }>("/healthz"),
  me: () => call<Me>(`/tenants/${DEMO_TENANT}/users/me`),
  tenant: () => call<Tenant>(`/tenants/${DEMO_TENANT}`),
  listAgents: () => call<AgentSummary[]>(`/tenants/${DEMO_TENANT}/agents`),
  getAgent: (id: string) => call<Record<string, unknown>>(`/tenants/${DEMO_TENANT}/agents/${id}`),
  triggerBrief: (forDate?: string) =>
    call<{ id: string; for_date: string; sections: BriefSection[]; total_cost_usd: number }>(
      `/tenants/${DEMO_TENANT}/briefs`,
      { method: "POST", body: JSON.stringify({ for_date: forDate ?? null }) },
    ),
  fetchBrief: (forDate: string) =>
    call<{ id: string; sections: BriefSection[]; total_cost_usd: number; for_date: string }>(
      `/tenants/${DEMO_TENANT}/briefs/${forDate}`,
    ),
  listApprovals: () => call<ApprovalRequest[]>(`/tenants/${DEMO_TENANT}/approvals`),
  decideApproval: (id: string, decision: "approved" | "denied", reason?: string) =>
    call<ApprovalRequest>(`/tenants/${DEMO_TENANT}/approvals/${id}/decide`, {
      method: "POST",
      body: JSON.stringify({ decision, reason }),
    }),
};

/**
 * SSE — streams brief sections as each specialist finishes. Returns a cleanup
 * function the caller invokes on unmount.
 */
export function streamBrief(
  forDate: string,
  handlers: {
    onStart?: (data: { agents: string[]; for_date: string; tenant: string }) => void;
    onSection?: (section: BriefSection) => void;
    onDone?: (data: { sections: BriefSection[]; total_cost_usd: number }) => void;
    onError?: (err: Error) => void;
  },
): () => void {
  let abort = new AbortController();

  (async () => {
    try {
      const res = await fetch(`/api/avengers/tenants/${DEMO_TENANT}/briefs/stream`, {
        method: "POST",
        headers: { ...authHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ for_date: forDate }),
        signal: abort.signal,
      });
      if (!res.ok || !res.body) {
        throw new Error(`stream ${res.status}`);
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        // SSE frame separator is "\n\n"
        let idx: number;
        while ((idx = buf.indexOf("\n\n")) !== -1) {
          const frame = buf.slice(0, idx);
          buf = buf.slice(idx + 2);
          const ev = parseSSE(frame);
          if (ev?.event === "start") handlers.onStart?.(ev.data);
          if (ev?.event === "section") handlers.onSection?.(ev.data);
          if (ev?.event === "done") handlers.onDone?.(ev.data);
        }
      }
    } catch (e) {
      if ((e as Error).name !== "AbortError") handlers.onError?.(e as Error);
    }
  })();

  return () => abort.abort();
}

function parseSSE(frame: string): { event: string; data: any } | null {
  const lines = frame.split("\n");
  let event = "message";
  const data: string[] = [];
  for (const line of lines) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).trim());
  }
  if (!data.length) return null;
  try {
    return { event, data: JSON.parse(data.join("\n")) };
  } catch {
    return { event, data: data.join("\n") };
  }
}

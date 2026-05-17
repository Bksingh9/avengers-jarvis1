"use client";

import useSWR from "swr";
import { toast } from "sonner";
import { Check, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";

export default function ApprovalsPage() {
  const { data, mutate, isLoading } = useSWR("approvals", () => api.listApprovals(), { refreshInterval: 5000 });

  const decide = async (id: string, decision: "approved" | "denied") => {
    try {
      await api.decideApproval(id, decision);
      toast.success(`Request ${decision}`);
      mutate();
    } catch (e) {
      toast.error("Decision failed", { description: (e as Error).message });
    }
  };

  return (
    <div className="space-y-6">
      <header>
        <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Human-in-the-loop</p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight">Approvals</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Any write to an external system pauses here until a human says go.
        </p>
      </header>

      {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}

      {data && data.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center justify-center gap-2 py-12 text-center text-sm text-muted-foreground">
            <span className="text-3xl">🌱</span>
            <p>No pending approvals.</p>
            <p className="text-xs">Triggered writes will show up here in real time.</p>
          </CardContent>
        </Card>
      )}

      <div className="space-y-3">
        {(data ?? []).map((r) => (
          <Card key={r.id}>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">{r.action}</CardTitle>
                <Badge tone={r.status === "pending" ? "warning" : "default"}>{r.status}</Badge>
              </div>
              <p className="text-xs text-muted-foreground">
                requested by <span className="text-foreground">agent:{r.requested_by_agent}</span> for {r.requested_for_user} · {new Date(r.created_at).toLocaleString()}
              </p>
            </CardHeader>
            <CardContent>
              <pre className="overflow-x-auto rounded-md bg-muted/40 p-3 text-xs">
                {JSON.stringify(r.payload, null, 2)}
              </pre>
              {r.status === "pending" && (
                <div className="mt-3 flex gap-2">
                  <Button size="sm" onClick={() => decide(r.id, "approved")}>
                    <Check size={14} /> Approve
                  </Button>
                  <Button size="sm" variant="destructive" onClick={() => decide(r.id, "denied")}>
                    <X size={14} /> Deny
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

"use client";

import useSWR from "swr";
import { motion } from "framer-motion";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { AGENT_META } from "@/lib/utils";
import { api } from "@/lib/api";

export default function AgentsPage() {
  const { data, error } = useSWR("agents-list", () => api.listAgents());

  return (
    <div className="space-y-6">
      <header>
        <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Specialists</p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight">Agent registry</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
          Each agent runs a bounded tool-use loop. Output is typed; every claim is sourced.
          Policies and human-in-the-loop rules are declarative — see <code className="rounded bg-muted px-1">config/agents/*.yaml</code>.
        </p>
      </header>

      {error && <p className="text-sm text-destructive">Failed to load agents: {(error as Error).message}</p>}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {(data ?? []).map((a, i) => {
          const meta = AGENT_META[a.id] ?? { label: a.display_name, color: "muted", icon: "•" };
          return (
            <motion.div
              key={a.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.04 }}
            >
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <span className="text-2xl">{meta.icon}</span>
                    {a.display_name}
                  </CardTitle>
                  <p className="text-xs text-muted-foreground">v{a.version}</p>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex flex-wrap gap-1.5">
                    <Badge tone="info">{a.model.split(":").slice(-1)[0]}</Badge>
                    {a.policies.map((p) => (
                      <Badge key={p} tone="default">{p}</Badge>
                    ))}
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}

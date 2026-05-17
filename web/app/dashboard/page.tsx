"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Zap } from "lucide-react";
import { toast } from "sonner";
import useSWR from "swr";
import { Button } from "@/components/ui/button";
import { CostTicker } from "@/components/brief/cost-ticker";
import { SectionCard } from "@/components/brief/section-card";
import { api, streamBrief, type BriefSection } from "@/lib/api";

const AGENT_ORDER = ["meetings", "markets", "security", "research", "content", "operations"];

export default function DashboardPage() {
  const today = useMemo(() => new Date().toISOString().slice(0, 10), []);
  const { data: tenant } = useSWR("tenant", () => api.tenant());
  const { data: agents } = useSWR("agents", () => api.listAgents());

  const [sections, setSections] = useState<Map<string, BriefSection>>(new Map());
  const [streaming, setStreaming] = useState(false);
  const [runningAgents, setRunningAgents] = useState<string[]>([]);
  const [totalCost, setTotalCost] = useState(0);

  const enabled = agents?.map((a) => a.id) ?? AGENT_ORDER;
  const orderedAgents = AGENT_ORDER.filter((a) => enabled.includes(a)).concat(
    enabled.filter((a) => !AGENT_ORDER.includes(a)),
  );

  const run = useCallback(() => {
    if (streaming) return;
    setSections(new Map());
    setTotalCost(0);
    setStreaming(true);
    toast.info("Generating brief…", { description: "Fanning out specialists." });

    const stop = streamBrief(today, {
      onStart: (d) => setRunningAgents(d.agents),
      onSection: (s) => {
        setSections((prev) => {
          const next = new Map(prev);
          next.set(s.agent, s);
          return next;
        });
        setTotalCost((t) => t + (s.cost_usd ?? 0));
      },
      onDone: () => {
        setStreaming(false);
        setRunningAgents([]);
        toast.success("Brief complete");
      },
      onError: (e) => {
        setStreaming(false);
        toast.error("Stream failed", { description: e.message });
      },
    });
    return stop;
  }, [streaming, today]);

  // Auto-run on first mount so the dashboard feels live.
  useEffect(() => {
    const stop = run();
    return () => stop?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const cap = tenant?.budgets.per_user_usd_cap ?? 1.5;

  return (
    <div className="space-y-6">
      <Hero
        date={today}
        running={streaming}
        runningCount={runningAgents.length}
        doneCount={sections.size}
        onRun={run}
      />

      <CostTicker total={totalCost} cap={cap} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-3">
        <AnimatePresence>
          {orderedAgents.map((agent) => {
            const section = sections.get(agent) ?? null;
            const pending = streaming && !section;
            return (
              <SectionCard key={agent} agent={agent} section={section} pending={pending} />
            );
          })}
        </AnimatePresence>
      </div>
    </div>
  );
}

function Hero({
  date,
  running,
  runningCount,
  doneCount,
  onRun,
}: {
  date: string;
  running: boolean;
  runningCount: number;
  doneCount: number;
  onRun: () => void;
}) {
  return (
    <div className="glass-strong relative overflow-hidden rounded-2xl p-6">
      <motion.div
        aria-hidden
        className="pointer-events-none absolute -right-12 -top-12 h-64 w-64 rounded-full bg-primary/30 blur-3xl"
        animate={{ scale: running ? [1, 1.15, 1] : 1, opacity: running ? [0.5, 0.8, 0.5] : 0.4 }}
        transition={{ repeat: Infinity, duration: 3 }}
      />
      <motion.div
        aria-hidden
        className="pointer-events-none absolute -left-12 -bottom-12 h-64 w-64 rounded-full bg-accent/30 blur-3xl"
        animate={{ scale: running ? [1, 1.2, 1] : 1, opacity: running ? [0.5, 0.8, 0.5] : 0.3 }}
        transition={{ repeat: Infinity, duration: 4, delay: 0.5 }}
      />

      <div className="relative flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
            Morning brief · {date}
          </p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight">
            {running ? "Composing your brief" : doneCount > 0 ? "Today, in one screen." : "Ready when you are."}
          </h1>
          <p className="mt-1 max-w-xl text-sm text-muted-foreground">
            {running
              ? `${doneCount} of ${runningCount} specialists finished — sections stream in as each completes.`
              : "Six specialists working in parallel, every claim sourced, every action auditable."}
          </p>
        </div>
        <Button onClick={onRun} disabled={running} size="lg" variant="accent">
          <Zap size={16} />
          {running ? "Streaming…" : "Run brief now"}
        </Button>
      </div>
    </div>
  );
}

"use client";

import { motion } from "framer-motion";
import { CheckCircle2, AlertTriangle, XCircle, Loader2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { AGENT_META, cn, formatCost, formatLatency } from "@/lib/utils";
import type { BriefSection, Cited } from "@/lib/api";

const STATUS_TONE = {
  ok: { tone: "success" as const, icon: CheckCircle2 },
  partial: { tone: "warning" as const, icon: AlertTriangle },
  skipped: { tone: "default" as const, icon: AlertTriangle },
  error: { tone: "destructive" as const, icon: XCircle },
};

interface Props {
  section: BriefSection | null;
  agent: string;
  pending?: boolean;
}

export function SectionCard({ section, agent, pending }: Props) {
  const meta = AGENT_META[agent] ?? { label: agent, color: "muted", icon: "•" };
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.25 }}
    >
      <Card className="relative overflow-hidden">
        <div
          className={cn(
            "absolute inset-x-0 top-0 h-1 transition-all",
            `bg-${meta.color}`,
          )}
        />
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2 text-base">
              <span className="text-lg">{meta.icon}</span>
              {meta.label}
            </CardTitle>
            {pending ? (
              <Badge tone="info" className="gap-1">
                <Loader2 size={11} className="animate-spin" />
                running
              </Badge>
            ) : section ? (
              <StatusBadge section={section} />
            ) : null}
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {pending && !section ? (
            <>
              <div className="shimmer h-3 w-full" />
              <div className="shimmer h-3 w-5/6" />
              <div className="shimmer h-3 w-3/4" />
            </>
          ) : section ? (
            <>
              <SectionBody section={section} />
              <div className="flex items-center justify-between border-t border-border/50 pt-3 text-[11px] text-muted-foreground">
                <span className="num">{formatLatency(section.latency_ms)}</span>
                <span className="num">{formatCost(section.cost_usd)}</span>
              </div>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">No data yet.</p>
          )}
        </CardContent>
      </Card>
    </motion.div>
  );
}

function StatusBadge({ section }: { section: BriefSection }) {
  const cfg = STATUS_TONE[section.status] ?? STATUS_TONE.ok;
  const Icon = cfg.icon;
  return (
    <Badge tone={cfg.tone} className="gap-1">
      <Icon size={11} />
      {section.status}
    </Badge>
  );
}

function SectionBody({ section }: { section: BriefSection }) {
  if (section.status === "error") {
    return (
      <p className="rounded-md bg-destructive/10 p-2 text-xs text-destructive">
        {section.error ?? "Section failed."}
      </p>
    );
  }
  const cited = collectCited(section.digest);
  if (cited.length === 0) {
    return <p className="text-sm text-muted-foreground">Nothing notable today.</p>;
  }
  return (
    <ul className="space-y-2">
      {cited.slice(0, 6).map((c, i) => (
        <li key={i} className="rounded-md bg-muted/40 p-2 text-sm">
          <p className="leading-snug">{c.text}</p>
          <div className="mt-1 flex flex-wrap gap-1">
            {c.sources.slice(0, 3).map((s, j) => (
              <span
                key={j}
                className="rounded-full bg-background/60 px-2 py-0.5 text-[10px] text-muted-foreground"
                title={s.ref}
              >
                {s.connector}·{s.tool}
              </span>
            ))}
          </div>
        </li>
      ))}
    </ul>
  );
}

function collectCited(digest: BriefSection["digest"]): Cited[] {
  const out: Cited[] = [];
  for (const value of Object.values(digest ?? {})) {
    if (Array.isArray(value)) {
      for (const item of value) {
        if (
          item &&
          typeof item === "object" &&
          "text" in item &&
          Array.isArray((item as Cited).sources)
        ) {
          out.push(item as Cited);
        }
      }
    }
  }
  return out;
}

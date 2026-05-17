"use client";

import { motion } from "framer-motion";
import { formatCost } from "@/lib/utils";

export function CostTicker({ total, cap }: { total: number; cap: number }) {
  const pct = Math.min(100, (total / cap) * 100);
  const tone = pct > 80 ? "bg-destructive" : pct > 50 ? "bg-warning" : "bg-success";
  return (
    <div className="glass flex w-full items-center gap-4 rounded-2xl p-4">
      <div className="flex-1">
        <div className="flex items-baseline justify-between">
          <span className="text-xs uppercase tracking-wider text-muted-foreground">
            Brief spend
          </span>
          <span className="num text-sm font-medium">{formatCost(total)} / {formatCost(cap)}</span>
        </div>
        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted/40">
          <motion.div
            className={`h-full ${tone}`}
            initial={{ width: 0 }}
            animate={{ width: `${pct}%` }}
            transition={{ duration: 0.6, ease: "easeOut" }}
          />
        </div>
      </div>
    </div>
  );
}

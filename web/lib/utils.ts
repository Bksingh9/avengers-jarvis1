import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCost(usd: number): string {
  if (usd < 0.01) return `$${(usd * 100).toFixed(2)}¢`;
  return `$${usd.toFixed(usd < 1 ? 3 : 2)}`;
}

export function formatLatency(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export const AGENT_META: Record<
  string,
  { label: string; color: string; icon: string }
> = {
  meetings:       { label: "Meetings",        color: "agent-meetings",       icon: "📅" },
  markets:        { label: "Markets",         color: "agent-markets",        icon: "📈" },
  security:       { label: "Security",        color: "agent-security",       icon: "🛡" },
  research:       { label: "Research",        color: "agent-research",       icon: "🔭" },
  content:        { label: "Content",         color: "agent-content",        icon: "✍" },
  operations:     { label: "Operations",      color: "agent-operations",     icon: "⚙" },
  // Fynd-specific (BRD §9.2)
  catalog:        { label: "Catalog",         color: "agent-catalog",        icon: "🏷" },
  inventory:      { label: "Inventory",       color: "agent-inventory",      icon: "📦" },
  reconciliation: { label: "Reconciliation",  color: "agent-reconciliation", icon: "🧾" },
};

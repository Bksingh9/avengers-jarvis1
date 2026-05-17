"use client";

import { Command } from "cmdk";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Calendar, Cog, FileSearch, Inbox, LayoutDashboard, Users, Zap } from "lucide-react";

type Action = { id: string; label: string; hint: string; icon: React.ReactNode; run: () => void };

export function CommandPalette({ onTriggerBrief }: { onTriggerBrief: () => void }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((x) => !x);
      }
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, []);

  const actions: Action[] = [
    { id: "dash",  label: "Open dashboard",   hint: "Today's brief",      icon: <LayoutDashboard size={16} />, run: () => router.push("/dashboard") },
    { id: "agents",label: "Browse agents",    hint: "6 specialists",      icon: <Users size={16} />,           run: () => router.push("/agents") },
    { id: "approv",label: "Approvals queue",  hint: "Human-in-the-loop",  icon: <Inbox size={16} />,           run: () => router.push("/approvals") },
    { id: "audit", label: "Audit log",        hint: "Append-only events", icon: <FileSearch size={16} />,      run: () => router.push("/audit") },
    { id: "set",   label: "Settings",         hint: "Delivery + budgets", icon: <Cog size={16} />,             run: () => router.push("/settings") },
    { id: "brief", label: "Run brief now",    hint: "Fan out specialists",icon: <Zap size={16} />,             run: () => onTriggerBrief() },
    { id: "today", label: "Jump to today",    hint: "Latest brief",       icon: <Calendar size={16} />,        run: () => router.push("/dashboard") },
  ];

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-background/60 pt-24 backdrop-blur"
      onClick={() => setOpen(false)}
    >
      <Command
        label="Command"
        className="glass-strong w-full max-w-xl rounded-2xl shadow-glow"
        onClick={(e) => e.stopPropagation()}
      >
        <Command.Input
          autoFocus
          placeholder="Type a command or search…"
          className="w-full bg-transparent px-5 py-4 text-base outline-none placeholder:text-muted-foreground"
        />
        <Command.List className="max-h-80 overflow-y-auto px-2 pb-2">
          <Command.Empty className="p-6 text-center text-sm text-muted-foreground">
            No matches.
          </Command.Empty>
          <Command.Group heading="Actions" className="px-2 pt-2 text-xs uppercase tracking-wider text-muted-foreground">
            {actions.map((a) => (
              <Command.Item
                key={a.id}
                onSelect={() => {
                  a.run();
                  setOpen(false);
                }}
                className="flex cursor-pointer items-center justify-between gap-3 rounded-md px-3 py-2 aria-selected:bg-muted aria-selected:text-foreground"
              >
                <span className="flex items-center gap-3 text-sm">
                  {a.icon}
                  {a.label}
                </span>
                <span className="text-xs text-muted-foreground">{a.hint}</span>
              </Command.Item>
            ))}
          </Command.Group>
        </Command.List>
        <div className="border-t border-border/60 px-4 py-2 text-[11px] text-muted-foreground">
          ⌘K to toggle · ↑↓ to navigate · ↵ to run · esc to close
        </div>
      </Command>
    </div>
  );
}

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, BookOpen, Cog, FileSearch, Inbox, LayoutDashboard, Mic, Sparkles, Users } from "lucide-react";
import { cn } from "@/lib/utils";

const nav = [
  { href: "/dashboard",  label: "Today",     icon: LayoutDashboard },
  { href: "/jarvis",     label: "JARVIS",    icon: Mic },
  { href: "/agents",     label: "Agents",    icon: Users },
  { href: "/approvals",  label: "Approvals", icon: Inbox },
  { href: "/audit",      label: "Audit",     icon: FileSearch },
  { href: "/settings",   label: "Settings",  icon: Cog },
  { href: "/setup",      label: "Setup",     icon: BookOpen },
];

export function Sidebar() {
  const path = usePathname();
  return (
    <aside className="glass-strong sticky top-4 hidden h-[calc(100vh-2rem)] w-60 flex-col rounded-2xl p-4 md:flex">
      <div className="mb-8 flex items-center gap-2 px-2">
        <div className="relative">
          <Sparkles className="text-primary" size={22} />
          <div className="absolute -inset-1 -z-10 rounded-full bg-primary/20 blur-md" />
        </div>
        <span className="text-lg font-semibold tracking-tight">AVENGERS</span>
      </div>

      <nav className="flex flex-col gap-1">
        {nav.map(({ href, label, icon: Icon }) => {
          const active = path?.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "group flex items-center gap-3 rounded-xl px-3 py-2 text-sm transition-all",
                active
                  ? "bg-primary/10 text-foreground shadow-glow"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground",
              )}
            >
              <Icon size={16} className={active ? "text-primary" : ""} />
              {label}
            </Link>
          );
        })}
      </nav>

      <div className="mt-auto rounded-xl border border-border/60 p-3 text-xs text-muted-foreground">
        <div className="flex items-center gap-2">
          <Activity size={12} className="text-success" />
          <span>Live · ⌘K to command</span>
        </div>
      </div>
    </aside>
  );
}

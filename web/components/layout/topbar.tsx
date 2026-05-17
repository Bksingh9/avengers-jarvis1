"use client";

import useSWR from "swr";
import { Search } from "lucide-react";
import { api } from "@/lib/api";

const fetcher = () => api.me();

export function Topbar() {
  const { data, error } = useSWR("me", fetcher);

  return (
    <header className="glass-strong sticky top-0 z-20 flex h-14 items-center justify-between rounded-2xl px-4 backdrop-blur">
      <button
        type="button"
        onClick={() => {
          document.dispatchEvent(new KeyboardEvent("keydown", { key: "k", metaKey: true }));
        }}
        className="flex items-center gap-2 rounded-full border border-border bg-muted/40 px-4 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
      >
        <Search size={14} />
        <span>Search or run a command…</span>
        <kbd className="ml-3 rounded bg-background/60 px-1.5 py-0.5 text-[10px]">⌘K</kbd>
      </button>

      <div className="flex items-center gap-3">
        {error ? (
          <span className="text-xs text-destructive">API offline</span>
        ) : data ? (
          <div className="flex items-center gap-3 text-sm">
            <div className="text-right">
              <div className="font-medium">{data.display_name}</div>
              <div className="text-xs text-muted-foreground">{data.tenant_id} · {data.timezone}</div>
            </div>
            <div className="grid h-9 w-9 place-items-center rounded-full bg-gradient-to-br from-primary to-accent text-sm font-semibold text-white">
              {data.display_name.slice(0, 1)}
            </div>
          </div>
        ) : (
          <div className="shimmer h-9 w-32 rounded-full" />
        )}
      </div>
    </header>
  );
}

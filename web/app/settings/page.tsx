"use client";

import useSWR from "swr";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { formatCost } from "@/lib/utils";

export default function SettingsPage() {
  const { data: me } = useSWR("me-settings", () => api.me());
  const { data: tenant } = useSWR("tenant-settings", () => api.tenant());

  return (
    <div className="space-y-6">
      <header>
        <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Profile</p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight">Settings</h1>
      </header>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Identity</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <Row k="Display name" v={me?.display_name} />
            <Row k="Email" v={me?.email} />
            <Row k="Tenant" v={me?.tenant_id} />
            <Row k="Timezone" v={me?.timezone} />
            <div className="pt-2">
              <p className="mb-1 text-xs text-muted-foreground">Groups</p>
              <div className="flex flex-wrap gap-1.5">
                {(me?.groups ?? []).map((g) => (
                  <Badge key={g} tone="info">{g}</Badge>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Tenant</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <Row k="Name" v={tenant?.name} />
            <Row k="Region" v={tenant?.region} />
            <Row k="Daily cap" v={tenant ? formatCost(tenant.budgets.daily_usd_cap) : undefined} />
            <Row k="Per-user cap" v={tenant ? formatCost(tenant.budgets.per_user_usd_cap) : undefined} />
            <div className="pt-2">
              <p className="mb-1 text-xs text-muted-foreground">Agents enabled</p>
              <div className="flex flex-wrap gap-1.5">
                {(tenant?.agents_enabled ?? []).map((a) => (
                  <Badge key={a}>{a}</Badge>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Delivery channels</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex flex-wrap gap-1.5">
              {(me?.delivery_prefs.channels ?? []).map((c) => (
                <Badge key={c} tone="info">{c}</Badge>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">
              Morning delivery at <span className="text-foreground">{me?.delivery_prefs.morning_time_local}</span> local.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function Row({ k, v }: { k: string; v?: string }) {
  return (
    <div className="flex justify-between gap-3 border-b border-border/40 py-1.5 last:border-0">
      <span className="text-muted-foreground">{k}</span>
      <span className="font-medium">{v ?? "—"}</span>
    </div>
  );
}

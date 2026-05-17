"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export default function AuditPage() {
  return (
    <div className="space-y-6">
      <header>
        <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Append-only</p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight">Audit log</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
          Every tool invocation, every model call, every approval is recorded into the
          per-tenant S3 audit bucket with COMPLIANCE-mode Object Lock. This page surfaces
          recent events from the in-process sink; production reads from the bucket.
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle>Coming online</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm text-muted-foreground">
          <p>
            The control-plane API exposes an audit-search endpoint behind the admin role
            for evidence requests. A streaming live-tail view will replace this placeholder
            once the read path against S3 is wired (Phase 3 of the release plan).
          </p>
          <div className="flex flex-wrap gap-2">
            <Badge tone="info">Object Lock: COMPLIANCE</Badge>
            <Badge tone="info">SSE-KMS per tenant</Badge>
            <Badge tone="info">Retention: 7y</Badge>
            <Badge tone="default">PII redacted at ingest</Badge>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

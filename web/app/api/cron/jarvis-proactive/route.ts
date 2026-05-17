/**
 * Vercel Cron entrypoint — fires at 01:30 UTC (07:00 IST) every day.
 *
 * Vercel sends `Authorization: Bearer ${CRON_SECRET}` from its scheduler to
 * this Next route. We forward the same secret to the FastAPI backend via the
 * `X-Cron-Secret` header, which `/jarvis/proactive` accepts as
 * non-user-bearing auth.
 *
 * Returns the backend's payload so Vercel Cron logs are useful.
 */

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const expected = process.env.CRON_SECRET;
  const auth = request.headers.get("authorization");
  if (expected && auth !== `Bearer ${expected}`) {
    return new Response("unauthorized", { status: 401 });
  }

  const tenant = process.env.JARVIS_TENANT ?? "jarvis";
  const base = process.env.AVENGERS_API_INTERNAL ?? "http://localhost:8080";
  const upstream = await fetch(`${base}/tenants/${tenant}/jarvis/proactive`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(expected ? { "X-Cron-Secret": expected } : {}),
    },
    body: "{}",
    cache: "no-store",
  });

  const text = await upstream.text();
  return new Response(text, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("Content-Type") ?? "application/json" },
  });
}

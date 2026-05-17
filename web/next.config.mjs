/** @type {import('next').NextConfig} */

// In production-on-Vercel, the top-level vercel.json rewrites /api/avengers/*
// to the Python serverless function — Next.js never sees those requests, so
// no rewrite here is needed.
//
// For local dev, the dashboard talks to the FastAPI backend on
// http://localhost:8080. We only register the Next.js rewrite when the env
// var explicitly opts in AND the value is a valid absolute URL — that way an
// empty / malformed Vercel env var can't fail the build with
// "destination does not start with /, http://, https://".

function buildRewrites() {
  const target = process.env.AVENGERS_API_INTERNAL;
  if (!target) return [];

  // Reject anything that isn't an absolute http(s) URL — Next.js will throw
  // "Invalid rewrite found" otherwise.
  const looksAbsolute = /^https?:\/\//.test(target);
  if (!looksAbsolute) {
    console.warn(
      `[next.config] AVENGERS_API_INTERNAL=${JSON.stringify(target)} is not an absolute URL — skipping rewrite.`,
    );
    return [];
  }

  // Strip a trailing slash so we don't end up with "https://host//path".
  const clean = target.replace(/\/+$/, "");

  return [
    {
      source: "/api/avengers/:path*",
      destination: `${clean}/:path*`,
    },
  ];
}

const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return buildRewrites();
  },
};

export default nextConfig;

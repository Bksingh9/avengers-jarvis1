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
  // Standalone output pre-traces only the modules Next.js actually needs at
  // runtime into .next/standalone/. Without this, Vercel's per-function nft
  // greedily scans all of node_modules — which dumped 423 MB of Node into
  // the Python function bundle and blew past the 250 MB serverless limit.
  output: "standalone",
  // Bump the trace root up to the repo root so excludes can target either
  // ./node_modules (the framework-detection shim) or ./web/node_modules.
  outputFileTracingRoot: process.cwd().endsWith("/web")
    ? process.cwd() + "/.."
    : process.cwd(),
  // Belt-and-braces: explicitly exclude dev-only / oversized deps from
  // any function bundle the trace produces.
  outputFileTracingExcludes: {
    "*": [
      "**/node_modules/typescript/**",
      "**/node_modules/@types/**",
      "**/node_modules/playwright-core/**",
      "**/node_modules/@playwright/**",
      "**/node_modules/tailwindcss/**",
      "**/node_modules/eslint/**",
      "**/node_modules/eslint-*/**",
      "**/node_modules/.cache/**",
      "**/.next/cache/**",
      // Kill any chance of the Python source / configs being swept into
      // a Next.js function bundle (they belong to the Python function).
      "src/**",
      "config/**",
      "prompts/**",
      "memory/**",
      "api/**",
    ],
  },
  async rewrites() {
    return buildRewrites();
  },
};

export default nextConfig;

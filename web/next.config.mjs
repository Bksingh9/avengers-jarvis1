/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: "/api/avengers/:path*",
        destination: `${process.env.AVENGERS_API_INTERNAL ?? "http://localhost:8080"}/:path*`,
      },
    ];
  },
};

export default nextConfig;

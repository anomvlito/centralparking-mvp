import type { NextConfig } from "next";

const BACKEND = (process.env.BACKEND_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000/api").replace(/\/api\/?$/, "");

const nextConfig: NextConfig = {
  rewrites: async () => [
    {
      source: "/api/:path*",
      destination: `${BACKEND}/api/:path*`,
    },
  ],
};

export default nextConfig;

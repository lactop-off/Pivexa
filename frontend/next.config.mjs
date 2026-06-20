/** @type {import('next').NextConfig} */
const API_PROXY = process.env.API_PROXY ?? "http://localhost:8000";

const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    // 開発時(`npm run dev`)に /api を FastAPI へプロキシする。
    // 本番(Docker)では nginx が /api をルーティングするため影響しない。
    return [{ source: "/api/:path*", destination: `${API_PROXY}/:path*` }];
  },
};

export default nextConfig;

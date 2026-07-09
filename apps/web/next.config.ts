import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Minimal self-contained server bundle for the production Docker image
  // (infra/docker-compose.prod.yml); no effect on `npm run dev`.
  output: "standalone",
};

export default nextConfig;

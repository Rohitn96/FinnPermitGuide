import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  env: {
    BACKEND_URL: process.env.BACKEND_URL || 'https://migriguide-api-759247877218.europe-north1.run.app',
  },
};

export default nextConfig;

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async redirects() {
    return [
      { source: "/onboarding/:path*", destination: "/dashboard", permanent: false },
    ];
  },
};

export default nextConfig;

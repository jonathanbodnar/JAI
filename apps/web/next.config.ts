import type { NextConfig } from "next";

const isDev = process.env.NODE_ENV === "development";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  typedRoutes: true,
  async headers() {
    return [
      {
        source: "/manifest.json",
        headers: [{ key: "Cache-Control", value: "public, max-age=0, must-revalidate" }],
      },
    ];
  },
};

// next-pwa wrapper is CJS; conditionally apply.
let exported: NextConfig = nextConfig;
if (!isDev) {
  try {
    const withPWA = require("next-pwa")({
      dest: "public",
      register: true,
      skipWaiting: true,
      disable: false,
    });
    exported = withPWA(nextConfig);
  } catch {
    exported = nextConfig;
  }
}

export default exported;

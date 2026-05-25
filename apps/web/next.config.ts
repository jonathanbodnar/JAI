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
// IMPORTANT: skipWaiting MUST be false. With skipWaiting=true, every SW
// update triggers an immediate page reload, which wipes in-flight React
// state (e.g. an open onboarding modal). With false, the new SW installs in
// the background and only takes over on the next natural navigation.
let exported: NextConfig = nextConfig;
if (!isDev) {
  try {
    const withPWA = require("next-pwa")({
      dest: "public",
      register: true,
      skipWaiting: false,
      disable: false,
    });
    exported = withPWA(nextConfig);
  } catch {
    exported = nextConfig;
  }
}

export default exported;

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  typedRoutes: true,
  async headers() {
    return [
      {
        // Manifest must always be fresh — needed for install / icons.
        source: "/manifest.json",
        headers: [{ key: "Cache-Control", value: "public, max-age=0, must-revalidate" }],
      },
      {
        // Ship a 410 SW so browsers permanently drop the legacy next-pwa
        // worker that was happily caching the entire app and preventing
        // hotfixes from reaching the user.
        source: "/sw.js",
        headers: [{ key: "Cache-Control", value: "no-store, max-age=0, must-revalidate" }],
      },
      {
        source: "/workbox-:hash.js",
        headers: [{ key: "Cache-Control", value: "no-store, max-age=0, must-revalidate" }],
      },
    ];
  },
};

// We deliberately do NOT use next-pwa right now. It was caching stale
// bundles, so hotfixes (e.g. the rebuild button) never reached users until
// they hard-cleared their browser. We can revisit a stricter offline story
// once the core flows are stable; for now we ship a self-unregistering SW
// stub (`apps/web/public/sw.js`) that wipes the previous one.
export default nextConfig;

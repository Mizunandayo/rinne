import type { NextConfig } from "next";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));

const nextConfig: NextConfig = {
  output: "standalone",
  outputFileTracingRoot: join(here, "../.."),
  reactStrictMode: true,
  poweredByHeader: false,
  productionBrowserSourceMaps: false,
  eslint: { ignoreDuringBuilds: false },
  typescript: { ignoreBuildErrors: false },
  experimental: {
    typedRoutes: true,
  },

  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          // Content-Security-Policy is NOT set here. It needs a per-request
          // nonce, so it lives in middleware.ts. Everything below is static.
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "no-referrer" },
          { key: "X-DNS-Prefetch-Control", value: "off" },
          { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
          { key: "Cross-Origin-Resource-Policy", value: "same-origin" },
          {
            key: "Permissions-Policy",
            // camera=(self) — the Day 6 cockpit needs it and nothing else does.
            value:
              "accelerometer=(), autoplay=(), camera=(self), display-capture=(), " +
              "encrypted-media=(), fullscreen=(self), geolocation=(), gyroscope=(), " +
              "magnetometer=(), microphone=(), midi=(), payment=(), usb=(), " +
              "xr-spatial-tracking=()",
          },
          {
            key: "Strict-Transport-Security",
            value: "max-age=63072000; includeSubDomains; preload",
          },
        ],
      },
    ];
  },
};

export default nextConfig;

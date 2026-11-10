
import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./i18n/request.ts");

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,

  /**
   * Phase 21 (audit finding 6.10) -- same-origin proxy for the API.
   *
   * lib/api.ts calls the relative path "/api/v1/...", which the browser
   * resolves against the origin that served the page; this rewrite forwards it
   * to the backend. Two consequences:
   *
   *  - No public API URL is compiled into the client bundle, so one image
   *    works in every environment and the Phase-18 blocker cannot recur.
   *  - Requests are same-origin, so CORS is not involved at all unless
   *    NEXT_PUBLIC_API_URL is used to make the browser call the API directly.
   *
   * BACKEND_INTERNAL_URL is deliberately SERVER-SIDE (no NEXT_PUBLIC_ prefix),
   * so it can never be inlined into the bundle and can never leak a backend
   * address or credential to the client. It defaults to the local dev backend,
   * which keeps `npm run dev` working with no configuration at all. In
   * docker-compose it is http://backend:8000.
   */
  async rewrites() {
    const backend = process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8000";
    return [{ source: "/api/v1/:path*", destination: `${backend}/api/v1/:path*` }];
  },

  // Allow access from other devices on the local network
  allowedDevOrigins: ["192.168.68.105"],

  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default withNextIntl(nextConfig);

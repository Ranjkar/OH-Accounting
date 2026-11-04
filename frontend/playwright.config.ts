import { defineConfig, devices } from "@playwright/test";

/** Phase 16: formal Playwright test suite (e2e/*.spec.ts), distinct from
 * the ad-hoc scratch scripts used for one-off manual verification
 * throughout this project's development (always deleted before commit,
 * see CLAUDE.md-equivalent session conventions).
 *
 * Requires BOTH the backend (python -m uvicorn app.main:app --port 8010)
 * and frontend (npm run dev -- --port 3000) dev servers already running
 * against the same dev database -- these tests exercise real login,
 * real API calls, and real rendered translations, not mocks. Does not
 * auto-start either server (a frontend-only `webServer` block would be
 * misleading here, since the backend is just as required). */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
});

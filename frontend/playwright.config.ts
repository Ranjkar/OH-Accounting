import { defineConfig, devices } from "@playwright/test";

/** Phase 16: formal Playwright test suite (e2e/*.spec.ts), distinct from
 * the ad-hoc scratch scripts used for one-off manual verification
 * throughout this project's development (always deleted before commit,
 * see CLAUDE.md-equivalent session conventions).
 *
 * Requires BOTH the backend (python -m uvicorn app.main:app --port 8010)
 * and frontend (BACKEND_INTERNAL_URL=http://localhost:8010 npm run dev --
 * --port 3000) dev servers already running against the same dev database
 * -- these tests exercise real login, real API calls, and real rendered
 * translations, not mocks. Does not auto-start either server (a
 * frontend-only `webServer` block would be misleading here, since the
 * backend is just as required).
 *
 * Projects: `chromium` runs everything on a desktop viewport. The device
 * projects run only e2e/responsive.spec.ts, each emulating one of the
 * target form factors (viewport, device scale factor, touch, user agent).
 * All device projects run on Chromium: the iPhone/iPad descriptors
 * default to WebKit, which is not installed in this environment, and the
 * layout/overflow/touch-target assertions in responsive.spec.ts depend on
 * CSS viewport width and touch emulation, not on the rendering engine.
 *
 * `workers: 1` is deliberate: every spec shares one test account whose
 * saved locale preference is server-side, so two specs running at once
 * would switch each other's language mid-test; and the backend login
 * endpoint is rate-limited (10/minute, see backend/app/core/config.py). */
const RESPONSIVE = /responsive\.spec\.ts/;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "iphone-se", testMatch: RESPONSIVE, use: { ...devices["iPhone SE"], defaultBrowserType: "chromium" } },
    { name: "iphone-15", testMatch: RESPONSIVE, use: { ...devices["iPhone 15"], defaultBrowserType: "chromium" } },
    { name: "pixel-7", testMatch: RESPONSIVE, use: { ...devices["Pixel 7"] } },
    { name: "ipad-mini", testMatch: RESPONSIVE, use: { ...devices["iPad Mini"], defaultBrowserType: "chromium" } },
    { name: "ipad", testMatch: RESPONSIVE, use: { ...devices["iPad (gen 7)"], defaultBrowserType: "chromium" } },
    { name: "ipad-pro-landscape", testMatch: RESPONSIVE, use: { ...devices["iPad Pro 11 landscape"], defaultBrowserType: "chromium" } },
    { name: "desktop-1920", testMatch: RESPONSIVE, use: { ...devices["Desktop Chrome"], viewport: { width: 1920, height: 1080 } } },
  ],
});

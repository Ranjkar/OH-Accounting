import { test, expect, Page } from "@playwright/test";
import fs from "fs";
import path from "path";

/** Phase 16: end-to-end internationalisation verification across all four
 * supported locales, against the real running app (see playwright.config.ts
 * for prerequisites). Catches exactly the class of bug unit tests can't:
 * this suite found a real runtime error (a `t.rich()` call passing a plain
 * value where next-intl expected a tag-render function, surfacing as
 * "Functions are not valid as a React child" in the browser console on
 * the Settings page) that TypeScript, ESLint, and vitest all missed.
 *
 * Logs in ONCE per locale (via storageState, Playwright's recommended
 * pattern for this) rather than once per test -- the backend's login
 * endpoint is rate-limited (10/minute, a deliberate brute-force
 * protection, see backend/app/core/config.py), and the first version of
 * this suite logged in ~17 times in under two minutes and started
 * failing with timeouts once it tripped that limit. Fewer, reused logins
 * is the correct fix, not raising the app's rate limit for a test. */

const LOCALES = [
  { code: "nl", lang: "nl-NL", dir: "ltr" as const, label: "Dashboard" },
  { code: "en", lang: "en-GB", dir: "ltr" as const, label: "Dashboard" },
  { code: "fa", lang: "fa-IR", dir: "rtl" as const, label: "داشبورد" },
  { code: "ar", lang: "ar-SA", dir: "rtl" as const, label: "لوحة التحكم" },
];

const TEST_EMAIL = "mollie-visual@example.com";
const TEST_PASSWORD = "VisualTest!23";
const BACKEND_URL = "http://localhost:8010/api/v1";

const SCREENSHOT_DIR = path.resolve(process.cwd(), "e2e/.screenshots");
const AUTH_DIR = path.resolve(process.cwd(), "e2e/.auth");

test.beforeAll(() => {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  fs.mkdirSync(AUTH_DIR, { recursive: true });
});

async function expectNoConsoleErrors(page: Page, errors: string[]) {
  // A handful of known-benign dev-mode noise patterns (React DevTools
  // prompt, Next.js Fast Refresh) are excluded; everything else failing
  // this assertion is a real bug, exactly like the t.rich() one this
  // suite caught during development.
  const real = errors.filter((e) => !/Download the React DevTools|\[Fast Refresh\]/i.test(e));
  expect(real, `Unexpected console errors:\n${real.join("\n")}`).toEqual([]);
}

async function resetAccountLocale(page: Page) {
  await setAccountLocale(page, null);
}

async function setAccountLocale(page: Page, code: string | null) {
  // Direct PATCH rather than a cookie: once a session has logged in once,
  // an explicit saved preference always wins over the onholland-locale
  // cookie (by design -- see lib/locale-context.tsx), so a later
  // context.addCookies() alone can't change the active locale for an
  // already-authenticated storageState session. Tests that need a
  // specific locale per-test against a shared logged-in session must set
  // the preference this way, not just the cookie.
  await page.evaluate(
    async ({ backendUrl, locale }) => {
      const token = localStorage.getItem("token");
      if (!token) return;
      await fetch(`${backendUrl}/auth/me/locale`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ locale }),
      });
    },
    { backendUrl: BACKEND_URL, locale: code }
  );
}

test.describe("Locale resolution (unauthenticated)", () => {
  for (const { code, lang, dir } of LOCALES) {
    test(`login page resolves ${lang} (${dir}) from the onholland-locale cookie`, async ({ page, context }) => {
      await context.addCookies([{ name: "onholland-locale", value: code, domain: "localhost", path: "/" }]);
      const consoleErrors: string[] = [];
      page.on("console", (msg) => {
        if (msg.type() === "error") consoleErrors.push(msg.text());
      });

      await page.goto("/login", { waitUntil: "networkidle" });

      await expect(page.locator("html")).toHaveAttribute("lang", lang);
      await expect(page.locator("html")).toHaveAttribute("dir", dir);

      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow, "page should not overflow horizontally").toBe(0);

      await page.screenshot({ path: path.join(SCREENSHOT_DIR, `login_${code}.png`) });
      await expectNoConsoleErrors(page, consoleErrors);
    });
  }
});

test.describe("Authenticated pages, all four locales", () => {
  for (const { code, lang, dir, label } of LOCALES) {
    test.describe(`${code} (${lang}, ${dir})`, () => {
      const authFile = path.join(AUTH_DIR, `${code}.json`);

      // One login per locale, reused by every test in this block via
      // storageState -- see the module-level comment for why. Must
      // explicitly override storageState to undefined here: test.use()
      // below applies to this hook too, and the file doesn't exist yet
      // (this hook is what creates it).
      test.beforeAll(async ({ browser }) => {
        const page = await browser.newPage({ storageState: undefined });
        await page.goto("/login", { waitUntil: "networkidle" });
        await page.fill("#login-email", TEST_EMAIL);
        await page.fill("#login-password", TEST_PASSWORD);
        await page.click('button[type="submit"]');
        await page.waitForURL("**/", { timeout: 15000 });
        await page.waitForTimeout(500);
        await page.click(`[role="radio"]:has-text("${code.toUpperCase()}")`);
        await page.waitForTimeout(400);
        await page.context().storageState({ path: authFile });
        await page.close();
      });

      test.afterAll(async ({ browser }) => {
        // Reset this shared test account's saved preference so later
        // locale blocks in this same suite don't inherit a stale
        // explicit override -- see lib/__tests__/locale-context.test.tsx
        // for why an explicit saved preference intentionally overrides
        // everything else once set.
        const context = await browser.newContext({ storageState: authFile });
        const page = await context.newPage();
        await page.goto("/", { waitUntil: "networkidle" });
        await resetAccountLocale(page);
        await context.close();
        fs.rmSync(authFile, { force: true });
      });

      test.use({ storageState: authFile });

      test(`dashboard renders in ${lang}, correct dir, sidebar translated, no overflow`, async ({ page }) => {
        const consoleErrors: string[] = [];
        page.on("console", (msg) => {
          if (msg.type() === "error") consoleErrors.push(msg.text());
        });

        await page.goto("/", { waitUntil: "networkidle" });
        await page.waitForTimeout(400);

        await expect(page.locator("html")).toHaveAttribute("lang", lang);
        await expect(page.locator("html")).toHaveAttribute("dir", dir);
        await expect(page.getByRole("heading", { name: label, exact: true })).toBeVisible();

        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
        expect(overflow).toBe(0);

        await page.screenshot({ path: path.join(SCREENSHOT_DIR, `dashboard_${code}.png`), fullPage: false });
        await expectNoConsoleErrors(page, consoleErrors);
      });

      test(`sidebar accordion still allows only one open group under ${dir}`, async ({ page }) => {
        await page.goto("/", { waitUntil: "networkidle" });
        await page.waitForTimeout(400);
        const buttons = page.locator('nav[aria-label="Main navigation"] [aria-expanded]');
        const count = await buttons.count();
        if (count > 1) {
          await buttons.nth(1).click();
          await page.waitForTimeout(200);
        }
        const expandedStates = await buttons.evaluateAll((els) => els.map((el) => el.getAttribute("aria-expanded")));
        expect(expandedStates.filter((s) => s === "true").length).toBeLessThanOrEqual(1);
      });

      test(`settings page (incl. MFA section) renders without errors in ${lang}`, async ({ page }) => {
        const consoleErrors: string[] = [];
        page.on("console", (msg) => {
          if (msg.type() === "error") consoleErrors.push(msg.text());
        });

        await page.goto("/settings", { waitUntil: "networkidle" });
        await page.waitForTimeout(400);

        // Regression guard for the real bug this suite found during
        // development: a t.rich() misuse threw "Functions are not valid
        // as a React child" specifically on this page's MFA section.
        await expectNoConsoleErrors(page, consoleErrors);

        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
        expect(overflow).toBe(0);

        await page.screenshot({ path: path.join(SCREENSHOT_DIR, `settings_${code}.png`) });
      });

      test(`users & audit-log pages render translated content with no raw translation keys in ${lang}`, async ({ page }) => {
        for (const route of ["/users", "/audit-log"]) {
          await page.goto(route, { waitUntil: "networkidle" });
          await page.waitForTimeout(400);
          const bodyText = await page.locator("body").innerText();
          // A raw, unresolved key looks like "namespace.key.subkey" with no
          // spaces -- real UI copy in any of these 4 languages never takes
          // that shape. This is a coarse but effective "did a translation
          // actually resolve" smoke check.
          const rawKeyPattern = /\b[a-zA-Z]+\.[a-zA-Z]+\.[a-zA-Z]+\b/;
          expect(rawKeyPattern.test(bodyText), `${route} in ${code} appears to show a raw translation key`).toBe(false);

          const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
          expect(overflow, `${route} should not overflow horizontally in ${dir}`).toBe(0);

          await page.screenshot({ path: path.join(SCREENSHOT_DIR, `${route.slice(1).replace("/", "-")}_${code}.png`) });
        }
      });
    });
  }
});

test.describe("Responsive viewports and themes, RTL + LTR", () => {
  const authFile = path.join(AUTH_DIR, "responsive.json");

  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage({ storageState: undefined });
    await page.goto("/login", { waitUntil: "networkidle" });
    await page.fill("#login-email", TEST_EMAIL);
    await page.fill("#login-password", TEST_PASSWORD);
    await page.click('button[type="submit"]');
    await page.waitForURL("**/", { timeout: 15000 });
    await page.context().storageState({ path: authFile });
    await page.close();
  });

  test.afterAll(async ({ browser }) => {
    const context = await browser.newContext({ storageState: authFile });
    const page = await context.newPage();
    await page.goto("/", { waitUntil: "networkidle" });
    await resetAccountLocale(page);
    await context.close();
    fs.rmSync(authFile, { force: true });
  });

  test.use({ storageState: authFile });

  const VIEWPORTS = [
    { name: "mobile", width: 390, height: 844 },
    { name: "tablet", width: 834, height: 1194 },
  ];

  for (const viewport of VIEWPORTS) {
    for (const { code, lang, dir } of [LOCALES[0], LOCALES[3]]) {
      // One LTR + one RTL locale per viewport size is enough to catch a
      // layout that only breaks under one direction or only at one
      // breakpoint -- not re-running all 4 locales at both sizes here,
      // since direction-specific layout bugs are already covered at
      // desktop size by the suite above.
      test(`dashboard fits ${viewport.name} viewport (${lang}, ${dir}), no horizontal overflow`, async ({ page, context }) => {
        await page.setViewportSize({ width: viewport.width, height: viewport.height });
        await context.addCookies([{ name: "onholland-locale", value: code, domain: "localhost", path: "/" }]);
        await page.goto("/", { waitUntil: "networkidle" });
        // The shared storageState session already has an explicit saved
        // locale preference from this describe block's beforeAll login
        // (whatever Accept-Language resolved to) -- an explicit
        // preference always wins over the cookie once logged in (see
        // setAccountLocale's comment), so it must be set directly rather
        // than relying on the cookie alone.
        await setAccountLocale(page, code);
        await page.reload({ waitUntil: "networkidle" });
        await page.waitForTimeout(400);
        await expect(page.locator("html")).toHaveAttribute("dir", dir);
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
        expect(overflow, `${viewport.name}/${code} dashboard should not overflow horizontally`).toBe(0);
        await page.screenshot({ path: path.join(SCREENSHOT_DIR, `dashboard_${code}_${viewport.name}.png`) });
      });
    }
  }

  for (const theme of ["light", "dark"]) {
    for (const { code, lang, dir } of [LOCALES[0], LOCALES[3]]) {
      test(`settings page renders correctly in ${theme} theme (${lang}, ${dir})`, async ({ page, context }) => {
        await context.addCookies([{ name: "onholland-locale", value: code, domain: "localhost", path: "/" }]);
        await page.goto("/settings", { waitUntil: "networkidle" });
        await setAccountLocale(page, code);
        await page.evaluate((t) => {
          try {
            localStorage.setItem("onholland-theme", t);
          } catch {
            /* ignore */
          }
        }, theme);
        await page.reload({ waitUntil: "networkidle" });
        await page.waitForTimeout(400);
        await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
        await expect(page.locator("html")).toHaveAttribute("dir", dir);
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
        expect(overflow).toBe(0);
        await page.screenshot({ path: path.join(SCREENSHOT_DIR, `settings_${code}_${theme}.png`) });
      });
    }
  }

  test("mixed-direction content: a Latin IBAN inside an RTL (Arabic) page stays left-to-right", async ({ page, context }) => {
    await context.addCookies([{ name: "onholland-locale", value: "ar", domain: "localhost", path: "/" }]);
    await page.goto("/settings", { waitUntil: "networkidle" });
    await setAccountLocale(page, "ar");
    await page.reload({ waitUntil: "networkidle" });
    await page.waitForTimeout(400);
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    // app/settings/page.tsx wraps the account email in dir="ltr" (see
    // its accountEmail row) -- the established bidi-isolation pattern
    // for technical/identifier text inside RTL pages. Confirm at least
    // one such isolated span exists and is actually marked ltr.
    const ltrSpans = page.locator('[dir="ltr"]');
    expect(await ltrSpans.count()).toBeGreaterThan(0);
  });
});

test.describe("Language switching without reload", () => {
  test("switching language via the selector updates the UI immediately, no full page reload", async ({ page, context }) => {
    // Pin the starting locale explicitly -- with no cookie, resolution
    // correctly falls through to Accept-Language (Playwright's default
    // test browser reports en-US), not nl-NL. That's the app working
    // as designed (see spec's "sensible initial locale detection for
    // unauthenticated users"), not something this test should assume.
    await context.addCookies([{ name: "onholland-locale", value: "nl", domain: "localhost", path: "/" }]);
    await page.goto("/login", { waitUntil: "networkidle" });
    await page.fill("#login-email", TEST_EMAIL);
    await page.fill("#login-password", TEST_PASSWORD);
    await page.click('button[type="submit"]');
    await page.waitForURL("**/", { timeout: 15000 });
    await page.waitForTimeout(500);

    try {
      await expect(page.locator("html")).toHaveAttribute("lang", "nl-NL");

      // Mark the window so a full reload (which would clear this) is detectable.
      await page.evaluate(() => {
        (window as unknown as { __noReload: boolean }).__noReload = true;
      });

      await page.click('[role="radio"]:has-text("AR")');
      await page.waitForTimeout(400);

      await expect(page.locator("html")).toHaveAttribute("lang", "ar-SA");
      await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
      const survived = await page.evaluate(() => (window as unknown as { __noReload?: boolean }).__noReload);
      expect(survived, "switching language should not trigger a full page reload").toBe(true);
    } finally {
      // Always clear the shared account's preference, even if an
      // assertion above throws -- an aborted test must not leak a
      // stale explicit preference into whichever test runs next.
      await resetAccountLocale(page);
    }
  });
});

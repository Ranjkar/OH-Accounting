import { test, expect, Page } from "@playwright/test";
import fs from "fs";
import path from "path";

/** Responsive / mobile readiness suite. Runs on every project in
 * playwright.config.ts (iPhone SE, iPhone 15, Pixel 7, iPad Mini, iPad,
 * iPad Pro landscape, desktop 1280 and 1920), against the real running app
 * (same prerequisites as i18n.spec.ts).
 *
 * What it asserts, per route and viewport:
 *   - no horizontal page overflow (documentElement.scrollWidth <= clientWidth)
 *   - no element sticking out of the viewport unless it sits inside an
 *     explicit horizontal scroll container (tables, <pre>)
 *   - no browser console errors (403s on the two role-gated pages excepted)
 *   - every visible button is at least 24px tall (WCAG 2.5.8)
 * plus the critical journeys: login, mobile navigation drawer, document
 * upload, invoice review, VAT return, RTL layout, reduced motion, and an
 * in-browser axe-core WCAG 2.2 AA scan of representative pages.
 *
 * Logs in once per project via storageState (the backend login endpoint
 * is rate-limited to 10/minute). */

const TEST_EMAIL = "mollie-visual@example.com";
const TEST_PASSWORD = "VisualTest!23";

const AUTH_DIR = path.resolve(process.cwd(), "e2e/.auth");
const SCREENSHOT_DIR = path.resolve(process.cwd(), "e2e/.screenshots/responsive");

/** Route inventory (every app/**\/page.tsx). Dynamic segments use ids
 * that exist in the seeded dev database for the test account's tenant. */
export const ROUTES = [
  "/", "/admin", "/admin/email", "/ai-intelligence", "/annual-statements", "/anomalies", "/assistant", "/audit-log",
  "/automation", "/balance-sheet", "/bank-transactions", "/banking", "/batches", "/batches/1", "/billing",
  "/budgets", "/calendar", "/cash-flow", "/categories", "/companies", "/companies/1", "/companies/1/workspace",
  "/companies/new",
  "/documents", "/documents/9", "/employee-portal", "/employees", "/entrepreneur-hours", "/financial-overview",
  "/forecasts", "/government", "/invitations/accept", "/kpis", "/ledger", "/ledger/1", "/legal-structure",
  "/loonheffingen", "/management-reports", "/payroll", "/profit-and-loss", "/purchases/upload", "/reconciliation",
  "/reports", "/review-centre", "/sales/upload", "/scenarios", "/settings", "/tax-centre", "/tax-optimization",
  "/reset-password", "/verify-email",
  "/trial-balance", "/users", "/users/invitations/accept", "/vat", "/vat/5", "/working-capital", "/working-hours",
];

// Pages gated to a role the test account does not have: the API answers
// 403 and the browser logs "Failed to load resource" -- expected, not a bug.
const ROLE_GATED = new Set(["/admin", "/admin/email", "/employee-portal"]);

function collectConsoleErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  return errors;
}

function realErrors(errors: string[], route: string) {
  return errors.filter((e) => {
    if (/Download the React DevTools|\[Fast Refresh\]|favicon/i.test(e)) return false;
    if (ROLE_GATED.has(route) && /403/.test(e)) return false;
    return true;
  });
}

/** Measures layout health in the page. Returns the page-level overflow in
 * px plus a short list of elements that extend past the viewport edge
 * without being inside a horizontal scroll container. */
async function layoutReport(page: Page) {
  return page.evaluate(() => {
    const de = document.documentElement;
    const vw = de.clientWidth;
    const inScroller = (el: Element) => {
      for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
        const o = getComputedStyle(p).overflowX;
        if (o === "auto" || o === "scroll" || o === "hidden") return true;
      }
      return false;
    };
    const offenders: string[] = [];
    for (const el of Array.from(document.querySelectorAll("body *"))) {
      const r = el.getBoundingClientRect();
      if (r.width === 0) continue;
      if ((r.right > vw + 1 || r.left < -1) && !inScroller(el)) {
        offenders.push(`<${el.tagName.toLowerCase()} class="${(el.getAttribute("class") ?? "").slice(0, 80)}"> ${Math.round(r.left)}..${Math.round(r.right)}`);
        if (offenders.length >= 5) break;
      }
    }
    const smallButtons: string[] = [];
    for (const el of Array.from(document.querySelectorAll<HTMLElement>("button"))) {
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) continue;
      if (r.height < 24) smallButtons.push(`"${(el.textContent ?? el.getAttribute("aria-label") ?? "").trim().slice(0, 30)}" ${Math.round(r.width)}x${Math.round(r.height)}`);
    }
    return { overflow: de.scrollWidth - vw, offenders, smallButtons, viewport: vw };
  });
}

async function expectHealthyLayout(page: Page, route: string, errors: string[]) {
  const r = await layoutReport(page);
  expect(r.overflow, `${route} @${r.viewport}px: page overflows horizontally`).toBeLessThanOrEqual(0);
  expect(r.offenders, `${route} @${r.viewport}px: elements outside the viewport`).toEqual([]);
  expect(r.smallButtons, `${route} @${r.viewport}px: buttons under 24px tall`).toEqual([]);
  expect(realErrors(errors, route), `${route}: console errors`).toEqual([]);
}

async function setAccountLocale(page: Page, locale: string | null) {
  await page.evaluate(async (loc) => {
    const token = localStorage.getItem("token");
    if (!token) return;
    await fetch("/api/v1/auth/me/locale", {
      method: "PATCH",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ locale: loc }),
    });
  }, locale);
}

test.beforeAll(() => {
  fs.mkdirSync(AUTH_DIR, { recursive: true });
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
});

test.describe("Login (unauthenticated)", () => {
  test("login form fits the viewport and signs in", async ({ page }, testInfo) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/login", { waitUntil: "networkidle" });
    await expectHealthyLayout(page, "/login", errors);

    // The whole form, including the submit button, is visible without
    // scrolling on every device (no control hidden below the fold).
    const submit = page.locator("button[type=submit]");
    await expect(submit).toBeInViewport();
    // Email field: 16px+ on touch devices so iOS does not auto-zoom on focus.
    if (testInfo.project.use.hasTouch) {
      const fontSize = await page.locator("#login-email").evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
      expect(fontSize).toBeGreaterThanOrEqual(16);
    }
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, `login_${testInfo.project.name}.png`) });

    await page.fill("#login-email", TEST_EMAIL);
    await page.fill("#login-password", TEST_PASSWORD);
    await submit.click();
    await page.waitForURL("**/", { timeout: 30000 });
    await expect(page.locator("h1").first()).toBeVisible();
    await expectHealthyLayout(page, "/", errors);
  });
});

test.describe("Authenticated", () => {
  let authFile: string;

  test.beforeAll(async ({ browser }, testInfo) => {
    authFile = path.join(AUTH_DIR, `responsive-${testInfo.project.name}.json`);
    const page = await browser.newPage({ storageState: undefined });
    await page.goto("/login", { waitUntil: "networkidle" });
    await page.fill("#login-email", TEST_EMAIL);
    await page.fill("#login-password", TEST_PASSWORD);
    await page.click("button[type=submit]");
    await page.waitForURL("**/", { timeout: 30000 });
    await setAccountLocale(page, "nl");
    await page.context().storageState({ path: authFile });
    await page.close();
  });

  test.beforeEach(async ({ context }) => {
    const state = JSON.parse(fs.readFileSync(authFile, "utf8"));
    await context.addCookies(state.cookies ?? []);
    for (const origin of state.origins ?? []) {
      await context.addInitScript((o) => {
        if (location.origin !== o.origin) return;
        for (const { name, value } of o.localStorage) localStorage.setItem(name, value);
      }, origin);
    }
  });

  test("every route renders without overflow, clipped controls or console errors", async ({ page }, testInfo) => {
    test.setTimeout(10 * 60 * 1000);
    const failures: string[] = [];
    for (const route of ROUTES) {
      const errors = collectConsoleErrors(page);
      await page.goto(route, { waitUntil: "networkidle" });
      await page.waitForTimeout(300);
      const r = await layoutReport(page);
      const errs = realErrors(errors, route);
      const problems = [
        r.overflow > 0 ? `overflow ${r.overflow}px` : null,
        r.offenders.length ? `outside viewport: ${r.offenders.join(" | ")}` : null,
        r.smallButtons.length ? `small buttons: ${r.smallButtons.join(" | ")}` : null,
        errs.length ? `console: ${errs.join(" | ")}` : null,
      ].filter(Boolean);
      if (problems.length) failures.push(`${route} @${r.viewport}px -> ${problems.join("; ")}`);
      if (["/", "/documents", "/ledger", "/vat/5", "/documents/9", "/settings"].includes(route)) {
        await page.screenshot({ path: path.join(SCREENSHOT_DIR, `${route.replace(/\//g, "_") || "_root"}_${testInfo.project.name}.png`) });
      }
    }
    expect(failures, failures.join("\n")).toEqual([]);
  });

  test("navigation: drawer on phones/tablets, rail on desktop", async ({ page }) => {
    await page.goto("/", { waitUntil: "networkidle" });
    const vw = page.viewportSize()!.width;
    const menuButton = page.getByRole("button", { name: /navigatie openen|open navigation/i });
    const rail = page.locator("aside.nav-rail-v2").first();

    if (vw >= 1024) {
      await expect(rail).toBeVisible();
      await expect(menuButton).toBeHidden();
      await expect(page.locator('nav a[aria-current="page"]')).toHaveCount(1);
      return;
    }

    await expect(menuButton).toBeVisible();
    await menuButton.click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    // Drawer never wider than the screen, anchored to the reading-start edge.
    const box = (await dialog.locator("aside").boundingBox())!;
    expect(box.width).toBeLessThanOrEqual(vw);
    expect(Math.round(box.x)).toBe(0);
    // Focus moved into the drawer; Escape closes it and returns focus.
    await expect(dialog.locator(":focus")).toHaveCount(1);
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    await expect(menuButton).toBeFocused();

    // Selecting a page closes the drawer and marks it active.
    await menuButton.click();
    const docsLink = dialog.locator('nav a[href="/documents"]');
    if (!(await docsLink.isVisible())) {
      // Accordion: open the group that holds the link.
      await dialog.locator("nav button[aria-expanded]").filter({ hasText: /documenten|documents/i }).first().click();
    }
    await docsLink.click();
    await page.waitForURL("**/documents");
    await expect(dialog).toBeHidden();
    await menuButton.click();
    await expect(dialog.locator('nav a[aria-current="page"]')).toHaveAttribute("href", "/documents");
    await page.keyboard.press("Escape");
  });

  test("document upload: file picker accepts photos and PDFs, selected files are listed", async ({ page }) => {
    await page.goto("/purchases/upload", { waitUntil: "networkidle" });
    const input = page.locator('input[type="file"]');
    await expect(input).toHaveAttribute("accept", /jpg|jpeg|png/);
    await expect(input).toHaveAttribute("multiple", "");
    await input.setInputFiles({ name: "receipt.jpg", mimeType: "image/jpeg", buffer: Buffer.from("not-really-a-jpeg") });
    await expect(page.getByText("receipt.jpg")).toBeVisible();
    // The upload button stays reachable (not off-screen) after a file is added.
    const upload = page.getByRole("button", { name: /upload/i }).last();
    await upload.scrollIntoViewIfNeeded();
    await expect(upload).toBeInViewport();
    const r = await layoutReport(page);
    expect(r.overflow).toBeLessThanOrEqual(0);
  });

  test("invoice review: preview and extracted fields usable at this width", async ({ page }) => {
    await page.goto("/documents/9", { waitUntil: "networkidle" });
    const vw = page.viewportSize()!.width;
    const preview = page.locator("iframe, img[alt]").first();
    const firstField = page.locator("form input").first();
    await expect(firstField).toBeVisible();
    const pBox = (await preview.boundingBox())!;
    const fBox = (await firstField.boundingBox())!;
    if (vw < 1024) {
      // Stacked: fields below the preview, not squeezed beside it.
      expect(fBox.y).toBeGreaterThan(pBox.y + pBox.height - 1);
    } else {
      expect(fBox.x).toBeGreaterThan(pBox.x + pBox.width - 1);
    }
    // Numeric fields get a numeric keyboard on phones.
    await expect(page.locator('form input[type="number"]').first()).toBeVisible();
    // The save button only renders for editable, non-final documents; when
    // present it must be reachable, not pushed off-screen by the preview.
    const save = page.locator('form button[type="submit"]');
    if (await save.count()) {
      await save.scrollIntoViewIfNeeded();
      await expect(save).toBeInViewport();
    }
  });

  test("VAT return: figures, status steps and export actions stay readable", async ({ page }) => {
    await page.goto("/vat/5", { waitUntil: "networkidle" });
    const r = await layoutReport(page);
    expect(r.overflow).toBeLessThanOrEqual(0);
    await expect(page.getByRole("button", { name: "pdf" })).toBeVisible();
    await expect(page.locator("table.table-v3").first()).toBeVisible();
    // Amount cells never wrap mid-value.
    const wraps = await page.locator("table.table-v3 td.text-right, table.table-v3 .col-amount").evaluateAll((cells) =>
      cells.filter((c) => getComputedStyle(c).whiteSpace !== "nowrap").length
    );
    expect(wraps).toBe(0);
  });

  test("financial tables scroll inside their container, never the page", async ({ page }) => {
    await page.goto("/ledger", { waitUntil: "networkidle" });
    const scroller = page.locator(".overflow-x-auto").first();
    await expect(scroller).toBeVisible();
    const r = await layoutReport(page);
    expect(r.overflow).toBeLessThanOrEqual(0);
    const info = await scroller.evaluate((el) => ({ scroll: el.scrollWidth, client: el.clientWidth, overflowX: getComputedStyle(el).overflowX }));
    expect(info.overflowX).toBe("auto");
    expect(info.scroll).toBeGreaterThanOrEqual(info.client);
  });

  test("RTL (Persian): mirrored layout without overflow, drawer on the right", async ({ page }) => {
    await page.goto("/", { waitUntil: "networkidle" });
    await setAccountLocale(page, "fa");
    try {
      for (const route of ["/", "/documents", "/ledger", "/vat/5", "/settings", "/companies/new"]) {
        await page.goto(route, { waitUntil: "networkidle" });
        await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
        const r = await layoutReport(page);
        expect(r.overflow, `${route} RTL overflow`).toBeLessThanOrEqual(0);
        expect(r.offenders, `${route} RTL offenders`).toEqual([]);
      }
      const vw = page.viewportSize()!.width;
      if (vw < 1024) {
        await page.goto("/", { waitUntil: "networkidle" });
        await page.getByRole("button", { name: /باز کردن|open navigation|navigatie/i }).click();
        const aside = page.getByRole("dialog").locator("aside");
        await expect(aside).toBeVisible();
        const box = (await aside.boundingBox())!;
        expect(Math.round(box.x + box.width)).toBe(vw);
        await page.keyboard.press("Escape");
      }
    } finally {
      await setAccountLocale(page, "nl");
    }
  });

  test("reduced motion is honoured", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/", { waitUntil: "networkidle" });
    const duration = await page.locator(".btn-primary-v2").first().evaluate((el) => getComputedStyle(el).transitionDuration);
    expect(parseFloat(duration)).toBeLessThan(0.01);
  });

  test("axe-core WCAG 2.2 AA scan of representative pages", async ({ page }) => {
    test.setTimeout(3 * 60 * 1000);
    const axeSource = fs.readFileSync(require.resolve("axe-core/axe.min.js"), "utf8");
    const violations: string[] = [];
    for (const route of ["/", "/documents", "/documents/9", "/ledger", "/vat/5", "/settings", "/users", "/purchases/upload", "/companies/new"]) {
      await page.goto(route, { waitUntil: "networkidle" });
      await page.addScriptTag({ content: axeSource });
      const result = await page.evaluate(async () => {
        // @ts-expect-error axe injected above
        const res = await window.axe.run(document, {
          runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] },
          rules: {
            // Dev-only Next.js overlay/portal is not part of the product UI.
            region: { enabled: false },
          },
        });
        return res.violations.map((v: { id: string; help: string; nodes: { target: string[] }[] }) => `[${v.id}] ${v.help}: ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(", ")}`);
      });
      for (const v of result) violations.push(`${route}: ${v}`);
    }
    expect(violations, violations.join("\n")).toEqual([]);
  });
});

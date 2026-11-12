import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

/** End-to-end company creation through the setup wizard, with isolated test
 * data: every row this spec creates is named with RUN_PREFIX and deleted
 * again in afterAll, straight from the database, because a company is
 * accounting data the API deliberately refuses to delete. */

const BASE = "http://localhost:3000";
const BACKEND = "http://localhost:8010/api/v1";
const TEST_EMAIL = "mollie-visual@example.com";
const TEST_PASSWORD = "VisualTest!23";
const AUTH = path.resolve(process.cwd(), "e2e/.auth/company-creation.json");
const RUN_PREFIX = `E2E-WIZARD-${Date.now()}-`;

const PYTHON = path.resolve(process.cwd(), "../backend/.venv/bin/python");

function deleteTestData(prefix: string) {
  execSync(
    `${PYTHON} - ${prefix} <<'PY'
import re, sys, psycopg
prefix = sys.argv[1]
url = "postgresql://onholland:onholland@localhost:5432/onholland_accounting"
try:
    raw = open("../backend/.env", encoding="utf-8").read()
    m = re.search(r"^DATABASE_URL=(.+)$", raw, re.M)
    if m:
        url = m.group(1).strip().replace("postgresql+psycopg://", "postgresql://")
except OSError:
    pass
with psycopg.connect(url) as c:
    like = (prefix + "%",)
    c.execute("delete from company_setup_drafts where created_company_id in (select id from companies where name like %s)", like)
    c.execute("delete from company_setup_drafts where data->>'name' like %s", like)
    # VAT periods hang off financial years, which hang off the company.
    c.execute("delete from vat_periods where financial_year_id in (select id from financial_years where company_id in (select id from companies where name like %s))", like)
    # Everything else that references companies, discovered from the schema so
    # a new FK cannot silently break test cleanup. Two passes: referencing
    # tables may themselves be referenced by rows deleted in the first pass.
    refs = c.execute(
        "select distinct tc.table_name, kcu.column_name from information_schema.table_constraints tc"
        " join information_schema.key_column_usage kcu on kcu.constraint_name = tc.constraint_name"
        " join information_schema.constraint_column_usage ccu on ccu.constraint_name = tc.constraint_name"
        " where tc.constraint_type = 'FOREIGN KEY' and ccu.table_name = 'companies' and ccu.table_name <> tc.table_name"
    ).fetchall()
    # Phase 26: a new company gets a draft agreement whose child rows reference
    # contracts, not companies, so the FK sweep below cannot see them.
    c.execute("delete from audit_logs where entity_type = 'contract' and entity_id in (select id from contracts where company_id in (select id from companies where name like %s))", like)
    for child in ("contract_reminders", "contract_events", "contract_signatures", "contract_signing_invitations", "contract_versions"):
        c.execute(f"delete from {child} where contract_id in (select id from contracts where company_id in (select id from companies where name like %s))", like)
    for _ in range(2):
        for table, column in refs:
            c.execute(f"delete from {table} where {column} in (select id from companies where name like %s)", like)
    n = c.execute("delete from companies where name like %s", like).rowcount
    c.commit()
    print("deleted companies:", n)
PY`,
    { cwd: path.resolve(process.cwd()), stdio: "pipe" }
  );
}

test.beforeAll(async ({ browser }) => {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.goto(`${BASE}/login`, { waitUntil: "networkidle" });
  await page.fill("#login-email", TEST_EMAIL);
  await page.fill("#login-password", TEST_PASSWORD);
  await page.click('button[type="submit"]');
  await page.waitForURL(BASE + "/", { timeout: 30000 });
  fs.mkdirSync(path.dirname(AUTH), { recursive: true });
  await ctx.storageState({ path: AUTH });
  await ctx.close();
});

test.afterAll(() => {
  deleteTestData(RUN_PREFIX);
});

// One company per run is enough; the journey is identical at every viewport
// and the responsive suite already sweeps /companies/new on all eight.
test.beforeEach(({ browserName }, testInfo) => {
  test.skip(browserName !== "chromium" || testInfo.project.name !== "chromium", "desktop-only journey");
});
test.describe.configure({ mode: "serial" });

test.describe("company creation through the setup wizard", () => {
  const companyName = RUN_PREFIX + "Bakkerij";

  test("a draft survives a reload and resumes where it stopped", async ({ browser }) => {
    const ctx = await browser.newContext({ storageState: AUTH });
    const page = await ctx.newPage();
    await page.goto(`${BASE}/companies/new`, { waitUntil: "networkidle" });
    await page.fill("#setup-name", companyName);
    await page.waitForTimeout(1200); // let the debounced autosave land
    await page.reload({ waitUntil: "networkidle" });
    await expect(page.locator("#setup-name")).toHaveValue(companyName);
    await ctx.close();
  });

  test("conditional rules block, then the wizard creates the company", async ({ browser }) => {
    const ctx = await browser.newContext({ storageState: AUTH });
    const page = await ctx.newPage();
    await page.goto(`${BASE}/companies/new`, { waitUntil: "networkidle" });
    await expect(page.locator("#setup-name")).toHaveValue(companyName);

    // A BV must register at the KVK: Next is refused until the number exists.
    await page.selectOption("#setup-legal-form", "bv");
    await page.locator("form button[type=submit]").last().click();
    await expect(page.locator("#setup-kvk")).toHaveAttribute("aria-invalid", "true");
    await expect(page.locator("#setup-kvk-error")).toBeVisible();

    // A VvE needs no KVK number, so the same step now passes.
    await page.selectOption("#setup-legal-form", "vve");
    await page.locator("form button[type=submit]").last().click();
    await page.waitForSelector("#setup-vat-registered", { timeout: 20000 });

    await page.locator("#setup-vat-registered button").nth(1).click(); // not VAT registered
    await page.selectOption("#setup-fy", String(new Date().getFullYear()));
    await page.locator("form button[type=submit]").last().click();
    await page.waitForSelector("#setup-iban", { timeout: 20000 });

    // An IBAN makes the account holder name conditionally required.
    await page.fill("#setup-iban", "NL91ABNA0417164300");
    await page.locator("form button[type=submit]").last().click();
    await expect(page.locator("#setup-bank-name-error")).toBeVisible();
    await page.locator("fieldset button.btn-ghost-v2").click(); // skip banking
    await page.waitForSelector("dl", { timeout: 20000 });

    await page.locator("form button[type=submit]").last().click(); // create
    await page.waitForURL(/\/companies\/\d+\?setup=done/, { timeout: 30000 });
    await expect(page.getByText(companyName).first()).toBeVisible();

    // The created company is listed, and its draft is no longer resumable.
    await page.goto(`${BASE}/companies`, { waitUntil: "networkidle" });
    await expect(page.getByText(companyName).first()).toBeVisible();
    await expect(page.getByText(companyName)).toHaveCount(1);
    await ctx.close();
  });
});

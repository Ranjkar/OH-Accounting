import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

/** Phase 26 end-to-end journey: admin drafts, approves and sends an agreement
 * for the seeded company; the client signs it on the public portal from a
 * fresh, unauthenticated browser context; the admin sees it signed with a
 * verifiable hash. Needs both dev servers (backend on :8010 started with
 * CONTRACTS_ENABLED=true, frontend on :3000) -- see playwright.config.ts.
 * Every row this spec creates is removed again in afterAll. */

const BASE = "http://localhost:3000";
const BACKEND = "http://localhost:8010/api/v1";
const TEST_EMAIL = "mollie-visual@example.com";
const TEST_PASSWORD = "VisualTest!23";
const COMPANY_ID = 1;
const AUTH = path.resolve(process.cwd(), "e2e/.auth/contracts.json");
const PYTHON = path.resolve(process.cwd(), "../backend/.venv/bin/python");
const SIGNER = { name: `E2E Signer ${Date.now()}`, email: `e2e-contract-${Date.now()}@example.com` };

let apiToken = "";
let contractId = 0;

function deleteTestData(signerEmail: string) {
  execSync(
    `${PYTHON} - ${signerEmail} <<'PY'
import re, sys, psycopg
email = sys.argv[1]
url = "postgresql://onholland:onholland@localhost:5432/onholland_accounting"
try:
    m = re.search(r"^DATABASE_URL=(.+)$", open("../backend/.env", encoding="utf-8").read(), re.M)
    if m:
        url = m.group(1).strip().replace("postgresql+psycopg://", "postgresql://")
except OSError:
    pass
with psycopg.connect(url) as c:
    ids = [r[0] for r in c.execute("select id from contracts where signer_email = %s", (email,)).fetchall()]
    if ids:
        c.execute("delete from contract_reminders where contract_id = any(%s)", (ids,))
        c.execute("delete from contract_events where contract_id = any(%s)", (ids,))
        c.execute("delete from contract_signatures where contract_id = any(%s)", (ids,))
        c.execute("delete from contract_signing_invitations where contract_id = any(%s)", (ids,))
        c.execute("delete from contract_versions where contract_id = any(%s)", (ids,))
        c.execute("delete from audit_logs where entity_type = 'contract' and entity_id = any(%s)", (ids,))
        c.execute("delete from contracts where id = any(%s)", (ids,))
    c.execute("delete from email_outbox where to_email = %s", (email,))
    c.commit()
    print("deleted contracts:", len(ids))
PY`,
    { cwd: process.cwd(), stdio: "pipe" }
  );
}

async function apiCall<T>(method: string, pathName: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BACKEND}${pathName}`, {
    method,
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${apiToken}` },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`${method} ${pathName} -> ${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}

test.beforeAll(async ({ browser }) => {
  const login = await fetch(`${BACKEND}/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: TEST_EMAIL, password: TEST_PASSWORD }) });
  apiToken = (await login.json()).access_token;
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

test.afterAll(() => deleteTestData(SIGNER.email));

test.beforeEach(({ browserName }, testInfo) => {
  test.skip(browserName !== "chromium" || testInfo.project.name !== "chromium", "desktop-only journey");
});
test.describe.configure({ mode: "serial" });

test.describe("annual agreement: draft, approve, send, sign", () => {
  test("admin creates a draft, completes the terms and approves it", async ({ browser }) => {
    const ctx = await browser.newContext({ storageState: AUTH });
    const page = await ctx.newPage();
    await page.goto(`${BASE}/contracts`, { waitUntil: "networkidle" });
    await page.getByRole("button", { name: /New contract|Nieuwe overeenkomst/ }).click();
    await page.selectOption("#contract-create-company", String(COMPANY_ID));
    await page.selectOption("#contract-create-language", "en");
    await page.locator("#contract-create-form button[type=submit]").click();
    await page.waitForURL(/\/contracts\/\d+$/, { timeout: 30000 });
    contractId = Number(page.url().split("/").pop());

    // Approval is blocked until the commercial terms and signer are set.
    await expect(page.getByRole("button", { name: /^(Approve|Goedkeuren)$/ })).toBeDisabled();
    await page.getByRole("button", { name: /Edit terms|Voorwaarden bewerken/ }).click();
    await page.fill("#ct-fee", "250");
    await page.fill("#ct-pay", "14");
    await page.fill("#ct-notice", "30");
    await page.fill("#ct-signer-name", SIGNER.name);
    await page.fill("#ct-signer-email", SIGNER.email);
    await page.getByRole("button", { name: /^(Save|Opslaan)$/ }).click();
    await expect(page.getByRole("button", { name: /^(Approve|Goedkeuren)$/ })).toBeEnabled({ timeout: 15000 });
    await page.getByRole("button", { name: /^(Approve|Goedkeuren)$/ }).click();
    await expect(page.getByText(/Ready to send|Klaar om te versturen/).first()).toBeVisible({ timeout: 15000 });
    await expect(page.getByText(/SHA-256: [0-9a-f]{64}/)).toBeVisible();
    await ctx.close();
  });

  test("sending yields a signing link (no email provider) and the client signs on the portal", async ({ browser }) => {
    const admin = await browser.newContext({ storageState: AUTH });
    const page = await admin.newPage();
    await page.goto(`${BASE}/contracts/${contractId}`, { waitUntil: "networkidle" });
    await page.getByRole("button", { name: /Send for signature|Versturen ter ondertekening/ }).click();
    const link = (await page.getByTestId("signing-link").textContent({ timeout: 15000 }))!.trim();
    expect(link).toMatch(/\/sign\/[A-Za-z0-9_-]{20,}$/);
    await admin.close();

    // The signer has no account: a fresh context with no storage state.
    const client = await browser.newContext();
    const sign = await client.newPage();
    await sign.goto(link, { waitUntil: "networkidle" });
    await expect(sign.getByRole("heading", { level: 1 })).toContainText(/Accounting Services Agreement|Overeenkomst administratieve dienstverlening/);
    await expect(sign.getByText(/not a qualified electronic signature|geen gekwalificeerde elektronische handtekening/i).first()).toBeVisible();
    const button = sign.getByRole("button", { name: /Sign agreement|Overeenkomst ondertekenen/ });
    await expect(button).toBeDisabled();
    await sign.fill("#sign-name", SIGNER.name);
    await sign.fill("#sign-email", SIGNER.email);
    await sign.check("#sign-consent");
    await button.click();
    await expect(sign.getByRole("heading", { level: 1, name: /Agreement signed|Overeenkomst ondertekend/ })).toBeVisible({ timeout: 20000 });
    await expect(sign.getByRole("link", { name: /Download signed PDF|Ondertekende PDF downloaden/ })).toBeVisible();
    // A replayed link shows the signed state, never a second signature form.
    await sign.reload({ waitUntil: "networkidle" });
    await expect(sign.getByRole("button", { name: /Sign agreement|Overeenkomst ondertekenen/ })).toHaveCount(0);
    await client.close();
  });

  test("the admin sees the signed agreement, evidence and a verified hash; signed terms are immutable", async ({ browser }) => {
    const ctx = await browser.newContext({ storageState: AUTH });
    const page = await ctx.newPage();
    await page.goto(`${BASE}/contracts/${contractId}`, { waitUntil: "networkidle" });
    await expect(page.getByText(/^(Signed|Ondertekend)$/).first()).toBeVisible();
    await expect(page.getByText(SIGNER.name).first()).toBeVisible();
    await expect(page.getByRole("button", { name: /Edit terms|Voorwaarden bewerken/ })).toHaveCount(0);
    const verifyButtons = page.getByRole("button", { name: /Verify hash|Hash controleren/ });
    await expect(verifyButtons).toHaveCount(2); // approved + signed version
    await verifyButtons.nth(1).click();
    await expect(page.getByText(/Integrity confirmed|Integriteit bevestigd/)).toBeVisible({ timeout: 15000 });
    // API-level immutability: editing a signed contract is refused.
    const res = await fetch(`${BACKEND}/contracts/${contractId}`, { method: "PATCH", headers: { "Content-Type": "application/json", Authorization: `Bearer ${apiToken}` }, body: JSON.stringify({ monthly_fee: "1" }) });
    expect(res.status).toBe(409);
    await ctx.close();
  });

  test("the company workspace shows the agreement on its Contracts tab", async ({ browser }) => {
    const ctx = await browser.newContext({ storageState: AUTH });
    const page = await ctx.newPage();
    await page.goto(`${BASE}/companies/${COMPANY_ID}/workspace`, { waitUntil: "networkidle" });
    await page.getByRole("tab", { name: /Contracts|Overeenkomsten/ }).click();
    const detail = await apiCall<{ reference: string }>("GET", `/contracts/${contractId}`);
    await expect(page.getByText(detail.reference).first()).toBeVisible({ timeout: 15000 });
    await ctx.close();
  });
});

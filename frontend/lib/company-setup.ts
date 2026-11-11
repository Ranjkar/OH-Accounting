/** Company setup wizard rules, mirrored from the backend so a step can be
 * blocked before a round trip:
 *
 *   - identifier formats/checksums  <- backend/app/core/dutch_identifiers.py
 *   - conditional required fields   <- validate_draft in
 *     backend/app/api/v1/company_setup.py
 *
 * The server stays authoritative: it re-runs the same checks on
 * `/companies/setup-drafts/{id}/validate` and `/complete`. Keeping these two
 * in one pure, framework-free module means the review step renders the same
 * message for a locally-rejected field and for an issue the server reports,
 * and it is unit-testable without rendering React (lib/__tests__).
 */

import type { LegalFormDefinition, SetupDraftData } from "./api";

export const SETUP_STEPS = ["details", "tax", "banking", "review"] as const;
export type SetupStep = (typeof SETUP_STEPS)[number];

/** Selects show these when the draft has not recorded an explicit choice;
 * the backend requires both once `vat_registered` is true, so the wizard
 * writes them into the draft instead of only displaying them. */
export const DEFAULT_VAT_FREQUENCY = "quarterly";
export const DEFAULT_VAT_ACCOUNTING_BASIS = "invoice_based";

export type SetupIssueCode = "required" | "invalid" | "duplicate";

/** Every field the wizard can report an issue for, named exactly as the
 * backend names them in SetupValidationIssue.field. */
export const SETUP_FIELDS = [
  "name",
  "legal_form_code",
  "kvk_number",
  "rsin",
  "address",
  "business_activity",
  "email",
  "phone",
  "vat_registered",
  "vat_number",
  "vat_frequency",
  "vat_accounting_basis",
  "kor_participant",
  "financial_year",
  "bank_iban",
  "bank_account_name",
] as const;
export type SetupField = (typeof SETUP_FIELDS)[number];

/** `errors.<field>.<code>` message keys that exist in the dictionaries, i.e.
 * the combinations validate_draft can actually emit. Anything outside this
 * set falls back to "<label>: <server message>" rather than to a missing-key
 * render, so a future backend rule degrades gracefully. */
export const KNOWN_ISSUE_KEYS: ReadonlySet<string> = new Set([
  "name.required",
  "name.duplicate",
  "legal_form_code.required",
  "legal_form_code.invalid",
  "kvk_number.required",
  "kvk_number.invalid",
  "kvk_number.duplicate",
  "rsin.invalid",
  "email.invalid",
  "vat_registered.required",
  "vat_number.required",
  "vat_number.invalid",
  "vat_frequency.required",
  "vat_accounting_basis.required",
  "kor_participant.invalid",
  "financial_year.required",
  "financial_year.invalid",
  "bank_iban.invalid",
  "bank_account_name.required",
]);

/** Dotted `companySetup` key for an issue, or null when we have no message
 * for that field/code combination. */
export function issueKey(field: string, code: string): string | null {
  const id = `${field}.${code}`;
  return KNOWN_ISSUE_KEYS.has(id) ? `errors.${id}` : null;
}

export function normalizeIdentifier(value: string | null | undefined): string {
  return (value ?? "").replace(/[\s.\-]/g, "").toUpperCase();
}

const KVK_RE = /^\d{8}$/;
const RSIN_RE = /^\d{9}$/;
const BTW_RE = /^NL\d{9}B\d{2}$/;
const IBAN_RE = /^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$/;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Elfproef: first eight digits weighted 9..2, minus the ninth, divisible by 11. */
function elfproef(digits: string): boolean {
  let total = 0;
  for (let i = 0; i < 8; i++) total += Number(digits[i]) * (9 - i);
  total -= Number(digits[8]);
  return ((total % 11) + 11) % 11 === 0;
}

/** ISO 7064 mod 97-10, chunked so the intermediate number stays exact. */
function mod97(value: string): number {
  const numeric = Array.from(value)
    .map((c) => (/[A-Z]/i.test(c) ? String(c.toUpperCase().charCodeAt(0) - 55) : c))
    .join("");
  let remainder = 0;
  for (let start = 0; start < numeric.length; start += 9) {
    remainder = Number(`${remainder}${numeric.slice(start, start + 9)}`) % 97;
  }
  return remainder;
}

export function isValidKvk(value: string | null | undefined): boolean {
  return KVK_RE.test(normalizeIdentifier(value));
}

export function isValidRsin(value: string | null | undefined): boolean {
  const v = normalizeIdentifier(value);
  return RSIN_RE.test(v) && elfproef(v);
}

export function isValidBtw(value: string | null | undefined): boolean {
  const v = normalizeIdentifier(value);
  return BTW_RE.test(v) && mod97(v) === 1;
}

export function isValidIban(value: string | null | undefined): boolean {
  const v = normalizeIdentifier(value);
  if (!IBAN_RE.test(v)) return false;
  if (v.startsWith("NL") && v.length !== 18) return false;
  return mod97(v.slice(4) + v.slice(0, 4)) === 1;
}

export function isValidEmail(value: string | null | undefined): boolean {
  return EMAIL_RE.test((value ?? "").trim());
}

/** Writes the tax defaults the selects display into the draft. Without this
 * the backend rejects a draft that looks complete on screen, because
 * `vat_frequency` / `vat_accounting_basis` are required once the company is
 * VAT-registered but were never sent. */
export function withTaxDefaults(data: SetupDraftData): SetupDraftData {
  if (!data.vat_registered) return data;
  if (data.vat_frequency && data.vat_accounting_basis) return data;
  return {
    ...data,
    vat_frequency: data.vat_frequency ?? DEFAULT_VAT_FREQUENCY,
    vat_accounting_basis: data.vat_accounting_basis ?? DEFAULT_VAT_ACCOUNTING_BASIS,
  };
}

function trim(value: string | null | undefined): string {
  return (value ?? "").trim();
}

/** One issue per field: the first rule that fires wins, so the wizard points
 * at the reason the user can act on (a missing KVK number, not its format).
 * Returns {} for the review step -- that step shows the server's verdict. */
export function validateSetupStep(
  step: SetupStep,
  data: SetupDraftData,
  legalForm: Pick<LegalFormDefinition, "requires_kvk_registration"> | null
): Record<string, SetupIssueCode> {
  const issues: Record<string, SetupIssueCode> = {};
  const add = (field: SetupField, code: SetupIssueCode) => {
    if (!(field in issues)) issues[field] = code;
  };

  if (step === "details") {
    if (!trim(data.name)) add("name", "required");
    if (!data.legal_form_code) add("legal_form_code", "required");
    const kvk = normalizeIdentifier(data.kvk_number) || null;
    if (legalForm?.requires_kvk_registration && !kvk) add("kvk_number", "required");
    if (kvk && !isValidKvk(kvk)) add("kvk_number", "invalid");
    const rsin = normalizeIdentifier(data.rsin) || null;
    if (rsin && !isValidRsin(rsin)) add("rsin", "invalid");
    if (trim(data.email) && !isValidEmail(data.email)) add("email", "invalid");
  }

  if (step === "tax") {
    if (data.vat_registered === undefined || data.vat_registered === null) add("vat_registered", "required");
    const btw = normalizeIdentifier(data.vat_number) || null;
    if (data.vat_registered && !btw) add("vat_number", "required");
    if (btw && !isValidBtw(btw)) add("vat_number", "invalid");
    if (data.vat_registered) {
      if (!data.vat_frequency) add("vat_frequency", "required");
      if (!data.vat_accounting_basis) add("vat_accounting_basis", "required");
    }
    if (data.kor_participant && data.vat_registered === false) add("kor_participant", "invalid");
    if (data.financial_year === undefined || data.financial_year === null) {
      add("financial_year", "required");
    } else if (data.financial_year < 2000 || data.financial_year > 2100) {
      add("financial_year", "invalid");
    }
  }

  if (step === "banking" && !data.bank_skipped) {
    const iban = normalizeIdentifier(data.bank_iban) || null;
    if (iban && !isValidIban(iban)) add("bank_iban", "invalid");
    if (iban && !trim(data.bank_account_name)) add("bank_account_name", "required");
  }

  return issues;
}

import { describe, expect, test } from "vitest";
import nl from "../../messages/nl.json";
import type { SetupDraftData } from "../api";
import {
  DEFAULT_VAT_ACCOUNTING_BASIS,
  DEFAULT_VAT_FREQUENCY,
  KNOWN_ISSUE_KEYS,
  SETUP_FIELDS,
  SETUP_STEPS,
  issueKey,
  isValidBtw,
  isValidEmail,
  isValidIban,
  isValidKvk,
  isValidRsin,
  normalizeIdentifier,
  validateSetupStep,
  withTaxDefaults,
} from "../company-setup";

// Same vectors the backend asserts in tests/test_company_setup.py: these two
// implementations must agree, or the wizard blocks a step the server would
// have accepted (or waves through one it will reject on /complete).
const VALID = { kvk: "6875 0110", btw: "NL000099998B57", rsin: "123456782", iban: "NL91ABNA0417164300" };
const INVALID = { kvk: "123", btw: "NL000099998B58", rsin: "123456783", iban: "NL91ABNA0417164301" };

const KVK_REQUIRED_FORM = { requires_kvk_registration: true };
const KVK_OPTIONAL_FORM = { requires_kvk_registration: false };

describe("normalizeIdentifier", () => {
  test("strips spaces, dots and dashes and upper-cases", () => {
    expect(normalizeIdentifier(" nl91 abna.0417-1643 00 ")).toBe("NL91ABNA0417164300");
  });

  test("tolerates null/undefined", () => {
    expect(normalizeIdentifier(null)).toBe("");
    expect(normalizeIdentifier(undefined)).toBe("");
  });
});

describe("Dutch identifier checks (mirror of backend/app/core/dutch_identifiers.py)", () => {
  test("KVK: exactly 8 digits, spacing allowed", () => {
    expect(isValidKvk(VALID.kvk)).toBe(true);
    expect(isValidKvk("68750110")).toBe(true);
    expect(isValidKvk(INVALID.kvk)).toBe(false);
    expect(isValidKvk("6875011A")).toBe(false);
    expect(isValidKvk("")).toBe(false);
  });

  test("RSIN: 9 digits passing the elfproef", () => {
    expect(isValidRsin(VALID.rsin)).toBe(true);
    expect(isValidRsin(INVALID.rsin)).toBe(false);
    expect(isValidRsin("12345678")).toBe(false);
  });

  test("BTW: NL + 9 digits + B + 2, passing ISO 7064 mod-97", () => {
    expect(isValidBtw(VALID.btw)).toBe(true);
    expect(isValidBtw(VALID.btw.toLowerCase())).toBe(true);
    expect(isValidBtw(INVALID.btw)).toBe(false);
    expect(isValidBtw("NL123456789B01")).toBe(false);
  });

  test("IBAN: mod-97 over the rearranged string, NL is 18 characters", () => {
    expect(isValidIban(VALID.iban)).toBe(true);
    expect(isValidIban("NL91 ABNA 0417 1643 00")).toBe(true);
    expect(isValidIban(INVALID.iban)).toBe(false);
    expect(isValidIban("NL91ABNA041716430")).toBe(false);
    expect(isValidIban("GB33BUKB20201555555555")).toBe(true);
  });

  test("email: only a shape check, the server does not enforce one", () => {
    expect(isValidEmail("boekhouder@voorbeeld.nl")).toBe(true);
    expect(isValidEmail("not-an-email")).toBe(false);
    expect(isValidEmail("")).toBe(false);
  });
});

describe("withTaxDefaults", () => {
  test("leaves a non-VAT draft untouched", () => {
    const data: SetupDraftData = { vat_registered: false };
    expect(withTaxDefaults(data)).toEqual(data);
  });

  test("records the frequency/basis the selects display, so /complete cannot fail on them", () => {
    const seeded = withTaxDefaults({ vat_registered: true });
    expect(seeded.vat_frequency).toBe(DEFAULT_VAT_FREQUENCY);
    expect(seeded.vat_accounting_basis).toBe(DEFAULT_VAT_ACCOUNTING_BASIS);
  });

  test("never overwrites an explicit choice", () => {
    const seeded = withTaxDefaults({ vat_registered: true, vat_frequency: "monthly", vat_accounting_basis: "cash_based" });
    expect(seeded.vat_frequency).toBe("monthly");
    expect(seeded.vat_accounting_basis).toBe("cash_based");
  });
});

describe("validateSetupStep: conditional required fields", () => {
  test("details requires a name and a legal form", () => {
    expect(validateSetupStep("details", {}, KVK_OPTIONAL_FORM)).toEqual({
      name: "required",
      legal_form_code: "required",
    });
  });

  test("KVK is required only for a legal form that must register at the KVK", () => {
    const base: SetupDraftData = { name: "Bakkerij Jansen", legal_form_code: "bv" };
    expect(validateSetupStep("details", base, KVK_REQUIRED_FORM).kvk_number).toBe("required");
    expect(validateSetupStep("details", base, KVK_OPTIONAL_FORM).kvk_number).toBeUndefined();
    expect(validateSetupStep("details", { ...base, kvk_number: VALID.kvk }, KVK_REQUIRED_FORM).kvk_number).toBeUndefined();
  });

  test("a KVK number that is present must be well formed, even when optional", () => {
    const issues = validateSetupStep("details", { name: "x", legal_form_code: "vve", kvk_number: INVALID.kvk }, KVK_OPTIONAL_FORM);
    expect(issues.kvk_number).toBe("invalid");
  });

  test("reports the missing KVK number, not its format, when both could apply", () => {
    const issues = validateSetupStep("details", { name: "x", legal_form_code: "bv", kvk_number: "  " }, KVK_REQUIRED_FORM);
    expect(issues.kvk_number).toBe("required");
  });

  test("RSIN is optional but a malformed one is rejected", () => {
    const base: SetupDraftData = { name: "x", legal_form_code: "bv" };
    expect(validateSetupStep("details", base, KVK_REQUIRED_FORM).rsin).toBeUndefined();
    expect(validateSetupStep("details", { ...base, rsin: INVALID.rsin }, KVK_REQUIRED_FORM).rsin).toBe("invalid");
    expect(validateSetupStep("details", { ...base, rsin: VALID.rsin }, KVK_REQUIRED_FORM).rsin).toBeUndefined();
  });

  test("an email that is present must look like an email", () => {
    const issues = validateSetupStep("details", { name: "x", legal_form_code: "bv", email: "info@" }, KVK_OPTIONAL_FORM);
    expect(issues.email).toBe("invalid");
  });

  test("tax requires an explicit VAT answer, then makes the btw-id conditional on it", () => {
    expect(validateSetupStep("tax", { financial_year: 2026 }, null).vat_registered).toBe("required");

    const registered = validateSetupStep("tax", { vat_registered: true, financial_year: 2026 }, null);
    expect(registered.vat_number).toBe("required");
    expect(registered.vat_frequency).toBe("required");
    expect(registered.vat_accounting_basis).toBe("required");

    const notRegistered = validateSetupStep("tax", { vat_registered: false, financial_year: 2026 }, null);
    expect(notRegistered.vat_number).toBeUndefined();
    expect(notRegistered.vat_frequency).toBeUndefined();
    expect(notRegistered.vat_accounting_basis).toBeUndefined();
  });

  test("a btw-id that is present is checksummed even for a non-VAT company", () => {
    const issues = validateSetupStep("tax", { vat_registered: false, vat_number: INVALID.btw, financial_year: 2026 }, null);
    expect(issues.vat_number).toBe("invalid");
  });

  test("a complete VAT-registered tax step passes", () => {
    const issues = validateSetupStep(
      "tax",
      withTaxDefaults({ vat_registered: true, vat_number: VALID.btw, financial_year: 2026 }),
      null
    );
    expect(issues).toEqual({});
  });

  test("the KOR cannot be claimed by a company that is not VAT-registered", () => {
    const issues = validateSetupStep("tax", { vat_registered: false, kor_participant: true, financial_year: 2026 }, null);
    expect(issues.kor_participant).toBe("invalid");
  });

  test("financial year is required and range-checked", () => {
    expect(validateSetupStep("tax", { vat_registered: false }, null).financial_year).toBe("required");
    expect(validateSetupStep("tax", { vat_registered: false, financial_year: 1999 }, null).financial_year).toBe("invalid");
    expect(validateSetupStep("tax", { vat_registered: false, financial_year: 2101 }, null).financial_year).toBe("invalid");
  });

  test("banking: an IBAN makes the account name required, and is checksummed", () => {
    expect(validateSetupStep("banking", {}, null)).toEqual({});
    expect(validateSetupStep("banking", { bank_iban: VALID.iban }, null).bank_account_name).toBe("required");
    expect(validateSetupStep("banking", { bank_iban: VALID.iban, bank_account_name: "Jansen" }, null)).toEqual({});
    expect(validateSetupStep("banking", { bank_iban: INVALID.iban, bank_account_name: "Jansen" }, null).bank_iban).toBe("invalid");
  });

  test("banking is skipped entirely once the user opts out, even with a stale IBAN", () => {
    const issues = validateSetupStep("banking", { bank_skipped: true, bank_iban: INVALID.iban }, null);
    expect(issues).toEqual({});
  });

  test("the review step defers to the server verdict", () => {
    expect(validateSetupStep("review", {}, null)).toEqual({});
  });
});

describe("issueKey", () => {
  test("maps a known field/code pair onto a companySetup message key", () => {
    expect(issueKey("kvk_number", "required")).toBe("errors.kvk_number.required");
    expect(issueKey("bank_account_name", "required")).toBe("errors.bank_account_name.required");
  });

  test("returns null for a combination with no message, so the UI can fall back", () => {
    expect(issueKey("address", "required")).toBeNull();
    expect(issueKey("name", "weird_new_code")).toBeNull();
  });

  test("every known key names a field the wizard renders", () => {
    for (const key of KNOWN_ISSUE_KEYS) {
      const field = key.split(".")[0];
      expect(SETUP_FIELDS, `issue key ${key} refers to an unknown field`).toContain(field);
    }
  });
});

/** The wizard renders a rule's message by looking up `companySetup.errors.<field>.<code>`,
 * so a rule without a dictionary entry would surface as a raw key path. These
 * tests are the coupling guard between validateSetupStep / KNOWN_ISSUE_KEYS
 * and the four dictionaries (nl.json is the source of truth for parity). */
const MESSAGES = nl as unknown as {
  companySetup: {
    fields: Record<string, string>;
    issueCodes: Record<string, string>;
    errors: Record<string, string | Record<string, string>>;
  };
};

function messageFor(field: string, code: string): string | undefined {
  const entry = MESSAGES.companySetup.errors[field];
  return typeof entry === "object" ? entry[code] : undefined;
}

describe("dictionary coverage for reported issues", () => {
  const DRAFTS: SetupDraftData[] = [
    {},
    { name: "   " },
    { name: "Bakkerij Jansen" },
    { name: "Bakkerij Jansen", legal_form_code: "bv" },
    { name: "Bakkerij Jansen", legal_form_code: "bv", kvk_number: INVALID.kvk },
    { name: "Bakkerij Jansen", legal_form_code: "bv", kvk_number: VALID.kvk, rsin: INVALID.rsin, email: "info@" },
    { vat_registered: true },
    { vat_registered: true, vat_number: INVALID.btw, financial_year: 1999 },
    { vat_registered: false, kor_participant: true, financial_year: 2026 },
    { vat_registered: false, vat_number: VALID.btw, financial_year: 2101 },
    { bank_iban: INVALID.iban },
    { bank_iban: VALID.iban },
    { bank_skipped: true, bank_iban: INVALID.iban },
  ];
  const FORMS = [KVK_REQUIRED_FORM, KVK_OPTIONAL_FORM, null];

  test("every rule the validator can fire has a translated message", () => {
    const fired = new Set<string>();
    for (const step of SETUP_STEPS) {
      for (const draft of DRAFTS) {
        for (const form of FORMS) {
          for (const [field, code] of Object.entries(validateSetupStep(step, draft, form))) {
            fired.add(`${field}.${code}`);
            expect(issueKey(field, code), `no issue key for ${field}.${code}`).not.toBeNull();
            expect(messageFor(field, code), `companySetup.errors.${field}.${code} is missing`).toBeTruthy();
          }
        }
      }
    }
    // Guard against this test silently degenerating into a no-op.
    expect(fired.size).toBeGreaterThan(8);
  });

  test("every known issue key resolves to a non-empty message", () => {
    for (const key of KNOWN_ISSUE_KEYS) {
      const [field, code] = key.split(".");
      expect(messageFor(field, code), `companySetup.errors.${key} is missing`).toBeTruthy();
    }
  });

  test("every field the wizard can report has a review label", () => {
    for (const field of SETUP_FIELDS) {
      expect(MESSAGES.companySetup.fields[field], `companySetup.fields.${field} is missing`).toBeTruthy();
    }
  });

  test("the three fallback issue codes are translated", () => {
    for (const code of ["required", "invalid", "duplicate"]) {
      expect(MESSAGES.companySetup.issueCodes[code], `companySetup.issueCodes.${code} is missing`).toBeTruthy();
    }
  });
});

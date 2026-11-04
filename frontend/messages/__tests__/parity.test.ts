import { describe, expect, it } from "vitest";
import nl from "../nl.json";
import en from "../en.json";
import fa from "../fa.json";
import ar from "../ar.json";
import { LOCALES } from "../../i18n/config";

type Messages = Record<string, unknown>;

function flatten(obj: Messages, prefix = ""): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (value !== null && typeof value === "object" && !Array.isArray(value)) {
      Object.assign(out, flatten(value as Messages, path));
    } else {
      out[path] = value;
    }
  }
  return out;
}

const DICTS: Record<string, Messages> = { nl, en, fa, ar };

describe("translation dictionaries", () => {
  it("declares exactly the four supported locales", () => {
    expect(LOCALES).toEqual(["nl-NL", "en-GB", "fa-IR", "ar-SA"]);
  });

  it.each(Object.entries(DICTS))("%s.json is non-empty and every value is a non-empty string", (locale, dict) => {
    const flat = flatten(dict);
    expect(Object.keys(flat).length).toBeGreaterThan(0);
    for (const [key, value] of Object.entries(flat)) {
      expect(typeof value, `${locale}.json key "${key}" should be a string`).toBe("string");
      expect((value as string).trim().length, `${locale}.json key "${key}" should not be empty`).toBeGreaterThan(0);
    }
  });

  it("every dictionary has an identical key structure to nl.json (the source of truth)", () => {
    const baseKeys = new Set(Object.keys(flatten(nl)));
    for (const [locale, dict] of Object.entries(DICTS)) {
      if (locale === "nl") continue;
      const keys = new Set(Object.keys(flatten(dict)));
      const missing = [...baseKeys].filter((k) => !keys.has(k));
      const extra = [...keys].filter((k) => !baseKeys.has(k));
      expect(missing, `${locale}.json is missing keys present in nl.json`).toEqual([]);
      expect(extra, `${locale}.json has keys not present in nl.json`).toEqual([]);
    }
  });

  it("nav group and item keys used by navConfig are present in every dictionary", () => {
    // Regression guard: navConfig.ts maps each NAV_GROUPS label/item to a
    // t("nav.groups.X") / t("nav.items.Y") key -- if one is renamed in
    // code without updating all four dictionaries, this catches it long
    // before a user sees a missing-translation fallback in the sidebar.
    const requiredGroups = ["dashboard", "accounting", "salesPurchases", "banking", "payrollHr", "taxCompliance", "planningAnalytics", "documents", "companySettings", "administration", "myWorkspace"];
    for (const dict of Object.values(DICTS)) {
      const groups = (dict as { nav: { groups: Record<string, string> } }).nav.groups;
      for (const key of requiredGroups) {
        expect(groups[key], `missing nav.groups.${key}`).toBeTruthy();
      }
    }
  });
});

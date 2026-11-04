import { describe, expect, it } from "vitest";
import fs from "fs";
import path from "path";
import { NAV_GROUPS, EMPLOYEE_ROLE_NAV_GROUPS } from "../navConfig";
import nlMessages from "../../../messages/nl.json";

const APP_DIR = path.resolve(import.meta.dirname, "../../../app");

function resolveKey(dotted: string): unknown {
  return dotted.split(".").reduce<unknown>((obj, part) => (obj && typeof obj === "object" ? (obj as Record<string, unknown>)[part] : undefined), nlMessages);
}

/** Regression guard for the brief's own explicit rule: "If a feature does
 * not exist, do not create a fake working page. Mark it as unavailable or
 * leave it out." Every nav item must be EXACTLY one of:
 *   - a real route (app<href>/page.tsx exists on disk), or
 *   - explicitly marked `unavailableKey` with an explanation.
 * Never both, never neither.
 *
 * Phase 16: labels are now translation keys (resolved via
 * useTranslations("nav.groups"/"nav.items") at render time), not literal
 * English text -- this test also verifies every labelKey/unavailableKey
 * referenced here actually resolves to a real string in nl.json, so a
 * typo'd key is caught here instead of silently falling back at runtime. */
describe("navConfig", () => {
  const allItems = [...NAV_GROUPS, ...EMPLOYEE_ROLE_NAV_GROUPS].flatMap((g) => g.items.map((item) => ({ ...item, group: g.labelKey })));

  it.each(allItems)("'$labelKey' (in $group) is a real route XOR marked unavailable", (item) => {
    const hasHref = !!item.href;
    const hasUnavailable = !!item.unavailableKey;
    expect(hasHref !== hasUnavailable).toBe(true);

    if (item.href) {
      const pagePath = path.join(APP_DIR, item.href === "/" ? "" : item.href, "page.tsx");
      expect(fs.existsSync(pagePath), `Expected ${pagePath} to exist for nav item '${item.labelKey}'`).toBe(true);
    }
  });

  it.each(allItems)("'$labelKey' resolves to a real nl.json translation", (item) => {
    expect(resolveKey(`nav.items.${item.labelKey}`), `nav.items.${item.labelKey} is missing from nl.json`).toBeTypeOf("string");
    if (item.unavailableKey) {
      expect(resolveKey(item.unavailableKey), `${item.unavailableKey} is missing from nl.json`).toBeTypeOf("string");
    }
  });

  it("every group has a resolvable label and at least one item", () => {
    for (const group of [...NAV_GROUPS, ...EMPLOYEE_ROLE_NAV_GROUPS]) {
      expect(resolveKey(`nav.groups.${group.labelKey}`), `nav.groups.${group.labelKey} is missing from nl.json`).toBeTypeOf("string");
      expect(group.items.length).toBeGreaterThan(0);
    }
  });

  it("no duplicate hrefs across the main nav (each real page listed once)", () => {
    const hrefs = NAV_GROUPS.flatMap((g) => g.items.map((i) => i.href)).filter(Boolean);
    expect(new Set(hrefs).size).toBe(hrefs.length);
  });
});

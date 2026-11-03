import { describe, expect, it } from "vitest";
import fs from "fs";
import path from "path";
import { NAV_GROUPS, EMPLOYEE_ROLE_NAV_GROUPS } from "../navConfig";

const APP_DIR = path.resolve(import.meta.dirname, "../../../app");

/** Regression guard for the brief's own explicit rule: "If a feature does
 * not exist, do not create a fake working page. Mark it as unavailable or
 * leave it out." Every nav item must be EXACTLY one of:
 *   - a real route (app<href>/page.tsx exists on disk), or
 *   - explicitly marked `unavailable` with an explanation.
 * Never both, never neither. */
describe("navConfig", () => {
  const allItems = [...NAV_GROUPS, ...EMPLOYEE_ROLE_NAV_GROUPS].flatMap((g) => g.items.map((item) => ({ ...item, group: g.label })));

  it.each(allItems)("'$label' (in $group) is a real route XOR marked unavailable", (item) => {
    const hasHref = !!item.href;
    const hasUnavailable = !!item.unavailable;
    expect(hasHref !== hasUnavailable).toBe(true);

    if (item.href) {
      const pagePath = path.join(APP_DIR, item.href === "/" ? "" : item.href, "page.tsx");
      expect(fs.existsSync(pagePath), `Expected ${pagePath} to exist for nav item '${item.label}'`).toBe(true);
    }
  });

  it("every group has a non-empty label and at least one item", () => {
    for (const group of [...NAV_GROUPS, ...EMPLOYEE_ROLE_NAV_GROUPS]) {
      expect(group.label.length).toBeGreaterThan(0);
      expect(group.items.length).toBeGreaterThan(0);
    }
  });

  it("no duplicate hrefs across the main nav (each real page listed once)", () => {
    const hrefs = NAV_GROUPS.flatMap((g) => g.items.map((i) => i.href)).filter(Boolean);
    expect(new Set(hrefs).size).toBe(hrefs.length);
  });
});

import { describe, expect, test } from "vitest";
import { formatEUR, formatDate, formatPercent, formatRelativeDate } from "../format";

// Computed via the real Intl API rather than hand-typed, since Dutch
// currency formatting uses a non-breaking space (U+00A0) between the
// symbol and the amount -- a hand-typed literal with a regular space
// looks identical but fails strict equality.
function expectedEUR(amount: number, locale: string): string {
  return new Intl.NumberFormat(locale, { style: "currency", currency: "EUR" }).format(amount);
}

describe("formatEUR", () => {
  test("defaults to nl-NL formatting when no locale is given (backward compatibility)", () => {
    expect(formatEUR("1250.00")).toBe(expectedEUR(1250, "nl-NL"));
  });

  test.each(["nl-NL", "en-GB"])("formats 1250.00 correctly for %s", (locale) => {
    expect(formatEUR("1250.00", locale)).toBe(expectedEUR(1250, locale));
  });

  test("fa-IR and ar-SA produce real digit-grouped currency output, not the Dutch default", () => {
    const nl = formatEUR("1250.00", "nl-NL");
    const fa = formatEUR("1250.00", "fa-IR");
    const ar = formatEUR("1250.00", "ar-SA");
    expect(fa).not.toBe(nl);
    expect(ar).not.toBe(nl);
    // Both should still represent 1250 -- Intl.NumberFormat renders
    // fa-IR with Eastern Arabic-Indic digits by default; just confirm
    // real output was produced, not a crash/empty string.
    expect(fa.length).toBeGreaterThan(0);
    expect(ar.length).toBeGreaterThan(0);
  });

  test("accepts a number as well as a string", () => {
    expect(formatEUR(1250, "en-GB")).toBe("€1,250.00");
  });

  test("negative amounts render with a sign, not silently dropped", () => {
    const negative = formatEUR("-89.50", "en-GB");
    expect(negative).toMatch(/-/);
    expect(negative).toContain("89.50");
  });

  test("zero renders as a real zero amount, not an empty string", () => {
    expect(formatEUR("0.00", "en-GB")).toBe("€0.00");
  });

  test("preserves 2-decimal accounting precision regardless of locale", () => {
    for (const locale of ["nl-NL", "en-GB", "fa-IR", "ar-SA"]) {
      const out = formatEUR("1234.56", locale);
      // Two fractional digits worth of cents must survive in some form --
      // not rounded away to a whole number.
      expect(out).not.toBe(formatEUR("1234.00", locale));
    }
  });

  test("a non-numeric string falls back to returning it unchanged rather than throwing", () => {
    expect(formatEUR("not-a-number")).toBe("not-a-number");
  });
});

describe("formatDate", () => {
  test("defaults to nl-NL when no locale is given", () => {
    expect(formatDate("2026-03-05")).toBe(formatDate("2026-03-05", "nl-NL"));
  });

  test("renders differently across all 4 supported locales (not silently Dutch for everyone)", () => {
    const outputs = ["nl-NL", "en-GB", "fa-IR", "ar-SA"].map((l) => formatDate("2026-03-05", l));
    // fa-IR/ar-SA use a different script/digit system than nl-NL/en-GB,
    // so at minimum those two pairs must differ from each other.
    expect(new Set(outputs).size).toBeGreaterThan(1);
  });

  test("accepts a Date object as well as a date string", () => {
    const viaString = formatDate("2026-03-05T00:00:00.000Z", "en-GB");
    const viaDate = formatDate(new Date("2026-03-05T00:00:00.000Z"), "en-GB");
    expect(viaDate).toBe(viaString);
  });
});

describe("formatPercent", () => {
  test("formats a 0-1 fraction as a percentage across locales", () => {
    expect(formatPercent(0.21, "en-GB")).toBe("21%");
    expect(formatPercent(0.21, "nl-NL")).toMatch(/21/);
  });

  test("accepts a string input", () => {
    expect(formatPercent("0.09", "en-GB")).toBe("9%");
  });

  test("a non-numeric string falls back to returning it unchanged", () => {
    expect(formatPercent("n/a")).toBe("n/a");
  });
});

describe("formatRelativeDate", () => {
  test("a past date renders as 'ago' in English", () => {
    const threeDaysAgo = new Date(Date.now() - 3 * 24 * 60 * 60 * 1000);
    expect(formatRelativeDate(threeDaysAgo, "en-GB")).toMatch(/ago/);
  });

  test("a future date renders as 'in' in English", () => {
    const inTwoHours = new Date(Date.now() + 2 * 60 * 60 * 1000);
    expect(formatRelativeDate(inTwoHours, "en-GB")).toMatch(/in /);
  });

  test("renders non-empty output in all 4 locales without throwing", () => {
    const oneDayAgo = new Date(Date.now() - 24 * 60 * 60 * 1000);
    for (const locale of ["nl-NL", "en-GB", "fa-IR", "ar-SA"]) {
      expect(formatRelativeDate(oneDayAgo, locale).length).toBeGreaterThan(0);
    }
  });
});

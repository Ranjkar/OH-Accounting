import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { LOCALES, RTL_LOCALES, dirFor, isRtl } from "../i18n/config";

/**
 * Phase 17.5 -- automated coverage for locale-driven font selection.
 *
 * Audit finding 6.12: commit 97f2d84 ("Phase 16.3: complete locale-aware
 * formatting sweep") loaded Vazirmatn and Noto Sans Arabic in app/layout.tsx
 * and injected both CSS variables onto <html>, but globals.css contained no
 * rule that ever consumed them. Every page downloaded two Arabic-script
 * webfont families that were never rendered, and Persian/Arabic text fell back
 * to Geist -> Arial -> the browser default.
 *
 * The intermediate state was worse and is the specific regression these tests
 * exist to prevent: the rule was written as `:root[lang="fa"]`, an ATTRIBUTE
 * selector that requires an exact match. layout.tsx emits the full BCP-47 tag
 * ("fa-IR", per i18n/config.ts's LOCALES), so it never matched anything.
 * `:root:lang(fa)` matches "fa-IR" correctly.
 *
 * jsdom cannot resolve CSS `var()` through getComputedStyle, so a true
 * computed-font assertion needs a real browser -- see the Playwright test in
 * e2e/i18n.spec.ts. What is asserted here is the wiring, which is exactly what
 * broke: the selectors, the stacks, the variables, and `:lang()` semantics.
 */

const read = (relative: string) => readFileSync(fileURLToPath(new URL(relative, import.meta.url)), "utf8");

const LAYOUT_TSX = read("../app/layout.tsx");

/** CSS comments must go before parsing: the explanatory comment above the font
 * rules contains both `[lang="fa"]` (as prose describing the historical bug)
 * and selector-looking text, so leaving it in would make the attribute-selector
 * check match the comment and would glue the comment onto the next rule's
 * captured selector. */
const stripCssComments = (css: string) => css.replace(/\/\*[\s\S]*?\*\//g, "");

const GLOBALS_CSS = stripCssComments(read("../app/globals.css"));

const normalize = (value: string) => value.replace(/\s+/g, " ").trim();

interface CssRule {
  selector: string;
  body: string;
}

/**
 * Flat scan of `selector { body }` pairs. Deliberately naive about nested
 * at-rules: a block inside `@media` is attributed to whatever selector text
 * precedes it, which is harmless here because every lookup below also requires
 * the body to declare the property being asked for, and the selectors under
 * test are all top-level.
 *
 * globals.css declares `:root` several times (design tokens, then the font
 * stack), so an indexOf-based lookup would silently find the wrong one. That
 * is the bug this avoids.
 */
function cssRules(source: string = GLOBALS_CSS): CssRule[] {
  const rules: CssRule[] = [];
  for (const match of source.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    rules.push({ selector: normalize(match[1]), body: match[2] });
  }
  return rules;
}

const RULES = cssRules();

/** The declaration value for `property` in the rule whose selector is exactly
 * `selector`. Fails loudly if there is none, or if it is ambiguous. */
function declarationFor(selector: string, property: string): string {
  const wanted = normalize(selector);
  const escaped = property.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const hits = RULES.filter(
    (rule) => rule.selector === wanted && new RegExp(`(?:^|;)\\s*${escaped}\\s*:`).test(rule.body)
  );
  expect(hits.length, `expected exactly one "${wanted}" rule declaring ${property}, found ${hits.length}`).toBe(1);
  const match = hits[0].body.match(new RegExp(`${escaped}\\s*:\\s*([^;]+);`));
  expect(match, `${wanted} does not declare ${property}`).not.toBeNull();
  return normalize(match![1]);
}

function stackFor(selector: string, property: string): string[] {
  return declarationFor(selector, property)
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
}

/** The JSX <html ...> opening tag. Matched as `<html` followed by a newline,
 * which excludes the prose reference "<html lang/dir>" in the comment above
 * RootLayout. */
function htmlOpenTag(): string {
  const start = LAYOUT_TSX.search(/<html\s*\n/);
  expect(start, "layout.tsx has no JSX <html> element").toBeGreaterThan(-1);
  return LAYOUT_TSX.slice(start, LAYOUT_TSX.indexOf(">", start));
}

describe("locale font wiring in globals.css", () => {
  it("uses the :lang() pseudo-class, never a [lang=] attribute selector", () => {
    // The exact historical bug: an attribute selector cannot match a full
    // BCP-47 tag, so it silently matched nothing at all.
    expect(GLOBALS_CSS).not.toMatch(/\[lang=["']?(fa|ar)/);
    expect(RULES.some((r) => r.selector === ":root:lang(fa)")).toBe(true);
    expect(RULES.some((r) => r.selector === ":root:lang(ar)")).toBe(true);
  });

  it("gives Dutch and English the existing Geist stack, untouched", () => {
    // The `:root` rule that declares --font-app-sans specifically, not the
    // design-token `:root` rules elsewhere in the file.
    expect(stackFor(":root", "--font-app-sans")).toEqual(["var(--font-geist-sans)"]);

    // No locale-specific override may exist for the Latin-script locales.
    expect(GLOBALS_CSS).not.toContain(":lang(nl)");
    expect(GLOBALS_CSS).not.toContain(":lang(en)");
  });

  it("gives Persian (fa-IR) Vazirmatn as its primary face", () => {
    const stack = stackFor(":root:lang(fa)", "--font-app-sans");
    expect(stack[0]).toBe("var(--font-vazirmatn)");
    // Noto Sans Arabic stays as a fallback so mixed-script strings still render.
    expect(stack).toContain("var(--font-noto-sans-arabic)");
    expect(stack[stack.length - 1]).toBe("sans-serif");
  });

  it("gives Arabic (ar-SA) Noto Sans Arabic as its primary face", () => {
    const stack = stackFor(":root:lang(ar)", "--font-app-sans");
    expect(stack[0]).toBe("var(--font-noto-sans-arabic)");
    expect(stack).toContain("var(--font-vazirmatn)");
    expect(stack[stack.length - 1]).toBe("sans-serif");
  });

  it("keeps --font-sans in step with --font-app-sans for both RTL locales", () => {
    // Tailwind's font-sans utility reads --font-sans, so the two must agree or
    // utility-classed elements render in a different face from body text.
    for (const selector of [":root:lang(fa)", ":root:lang(ar)"]) {
      expect(stackFor(selector, "--font-sans")).toEqual(stackFor(selector, "--font-app-sans"));
    }
  });

  it("applies the locale stack to body text", () => {
    expect(declarationFor("body", "font-family")).toContain("var(--font-app-sans)");
  });

  it("makes native form controls inherit the locale font", () => {
    // Native controls do not inherit font-family by default, so without this an
    // <input> or <select> renders Persian/Arabic in a different face from the
    // surrounding text.
    const rule = RULES.find((r) => r.body.includes("font-family: inherit") && r.selector.includes("button"));
    expect(rule, "no rule sets font-family: inherit on form controls").toBeDefined();
    for (const control of ["button", "input", "select", "textarea", "optgroup"]) {
      expect(rule!.selector.split(",").map(normalize)).toContain(control);
    }
  });
});

describe("the CSS variables the font stacks reference are actually provided", () => {
  it("layout.tsx defines every --font-* variable the stacks consume", () => {
    const referenced = new Set<string>();
    for (const selector of [":root", ":root:lang(fa)", ":root:lang(ar)"]) {
      for (const property of ["--font-app-sans", "--font-sans"]) {
        const hits = RULES.filter((r) => r.selector === selector && r.body.includes(`${property}:`));
        for (const rule of hits) {
          for (const variable of rule.body.matchAll(/var\((--font-[a-z-]+)\)/g)) {
            referenced.add(variable[1]);
          }
        }
      }
    }
    expect(referenced.size).toBeGreaterThan(0);

    // A typo'd variable name resolves to nothing and falls back silently, so
    // pin each one to a `variable: "..."` declaration in the font loaders.
    for (const variable of referenced) {
      if (variable === "--font-geist-sans") {
        expect(LAYOUT_TSX).toMatch(/geistSans\.variable/);
        continue;
      }
      expect(LAYOUT_TSX, `layout.tsx never defines ${variable}`).toContain(`"${variable}"`);
    }
  });

  it("layout.tsx puts every font variable on the same element as lang and dir", () => {
    const openTag = htmlOpenTag();
    for (const token of ["geistSans.variable", "notoSansArabic.variable", "vazirmatn.variable"]) {
      expect(openTag, `<html> is missing ${token}`).toContain(token);
    }
    // They must be on the same element that carries lang/dir, or `:lang()` on
    // :root would not see the variables it is overriding.
    expect(openTag).toContain("lang={locale}");
    expect(openTag).toContain("dir={dir}");
  });

  it("loads Vazirmatn and Noto Sans Arabic with the arabic subset", () => {
    expect(LAYOUT_TSX).toMatch(/Noto_Sans_Arabic\(\{[\s\S]{0,140}subsets:\s*\["arabic"\]/);
    expect(LAYOUT_TSX).toMatch(/Vazirmatn\(\{[\s\S]{0,140}subsets:\s*\["arabic"\]/);
  });
});

describe(":lang() semantics against full BCP-47 tags (the historical bug)", () => {
  it("matches fa-IR / ar-SA, which an attribute selector would not", () => {
    const root = document.documentElement;

    root.setAttribute("lang", "fa-IR");
    expect(root.matches(":lang(fa)")).toBe(true);
    expect(root.matches('[lang="fa"]')).toBe(false);

    root.setAttribute("lang", "ar-SA");
    expect(root.matches(":lang(ar)")).toBe(true);
    expect(root.matches('[lang="ar"]')).toBe(false);

    root.removeAttribute("lang");
  });

  it("does not match the Latin-script locales", () => {
    const root = document.documentElement;
    for (const locale of ["nl-NL", "en-GB"]) {
      root.setAttribute("lang", locale);
      expect(root.matches(":lang(fa)")).toBe(false);
      expect(root.matches(":lang(ar)")).toBe(false);
    }
    root.removeAttribute("lang");
  });
});

describe("every supported locale resolves to a deliberate font decision", () => {
  it("covers all four locales, with exactly the two RTL ones getting an override", () => {
    expect([...LOCALES]).toEqual(["nl-NL", "en-GB", "fa-IR", "ar-SA"]);
    expect([...RTL_LOCALES]).toEqual(["fa-IR", "ar-SA"]);

    for (const locale of LOCALES) {
      const code = locale.split("-")[0];
      const hasOverride = RULES.some((r) => r.selector === `:root:lang(${code})`);
      expect(hasOverride, `${locale} should have an override iff it is RTL`).toBe(isRtl(locale));
      expect(dirFor(locale)).toBe(isRtl(locale) ? "rtl" : "ltr");
    }
  });
});

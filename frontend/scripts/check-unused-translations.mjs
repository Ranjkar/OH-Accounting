#!/usr/bin/env node
// Phase 16.1: heuristic unused-translation-key report. Flags dictionary
// keys with no apparent call site, so a leftover/renamed key gets
// noticed instead of silently accumulating forever.
//
// This is NOT a hard CI gate (unlike check-translation-parity.mjs) and
// never exits non-zero: full static certainty would need a real
// TS/JSX AST walk that resolves which `useTranslations(ns)` result
// each `t(...)` call belongs to, plus specifically understanding that
// components/glass/navConfig.ts stores translation keys as plain string
// values (labelKey/unavailableKey) resolved dynamically at render time
// via `t(item.labelKey as never)`, not as a literal argument to any
// t() call. A regex-based scan over-reports false positives for any
// key only ever referenced that way (or via other dynamic
// `t(variable)` patterns), so this script's output is a worklist for a
// human to sanity-check, not an enforced guarantee.
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const NL = JSON.parse(fs.readFileSync(path.join(ROOT, "messages/nl.json"), "utf8"));

function flatten(obj, prefix = "", out = {}) {
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === "object" && !Array.isArray(v)) flatten(v, key, out);
    else out[key] = v;
  }
  return out;
}

function walk(dir, files = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (["node_modules", ".next", ".git", "e2e", ".i18n-fragments"].includes(entry.name)) continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(full, files);
    else if (/\.(tsx?|mjs|js)$/.test(entry.name) && !entry.name.endsWith(".test.tsx") && !entry.name.endsWith(".test.ts")) {
      files.push(full);
    }
  }
  return files;
}

const sourceFiles = walk(path.join(ROOT, "app")).concat(walk(path.join(ROOT, "components")), walk(path.join(ROOT, "lib")));
let allSource = "";
for (const f of sourceFiles) allSource += fs.readFileSync(f, "utf8") + "\n";

// Every quoted string literal anywhere that looks like it could be a
// translation key or namespace argument -- deliberately broad, since
// false negatives (missing a real usage) are worse here than false
// positives (a few strings that happen to match a key name by
// coincidence).
const literalPattern = /["'`]([a-zA-Z][a-zA-Z0-9_.]*)["'`]/g;
const literals = new Set();
let m;
while ((m = literalPattern.exec(allSource))) literals.add(m[1]);

const flat = flatten(NL);
const unused = [];
for (const dottedKey of Object.keys(flat)) {
  const segments = dottedKey.split(".");
  const lastSegment = segments[segments.length - 1];
  // "used" if: the full dotted path appears literally, OR the last
  // segment appears literally AND its namespace root also appears
  // literally somewhere (covers useTranslations("ns") + t("leafKey")
  // split across two call sites, including nested namespaces).
  const usedDirectly = literals.has(dottedKey);
  const usedViaNamespaceSplit = literals.has(lastSegment) && literals.has(segments[0]);
  if (!usedDirectly && !usedViaNamespaceSplit) unused.push(dottedKey);
}

if (unused.length === 0) {
  console.log("[i18n] no obviously-unused keys found (heuristic scan)");
} else {
  console.log(`[i18n] ${unused.length} key(s) with no detected call site (heuristic -- verify manually before deleting):`);
  for (const k of unused) console.log(`  - ${k}`);
}

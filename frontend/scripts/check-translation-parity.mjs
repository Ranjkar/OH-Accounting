#!/usr/bin/env node
/** Phase 16: fails (non-zero exit) if the four message dictionaries don't
 * share an identical key structure, or if any value is empty/not a
 * string where a string is expected. Run in CI and locally
 * (`npm run check:i18n`) -- the same check also runs as a vitest test
 * (messages/__tests__/parity.test.ts) so it's caught by `npm test` too,
 * not just a separate script someone has to remember to run. */
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const LOCALES = ["nl", "en", "fa", "ar"];
const MESSAGES_DIR = path.join(__dirname, "..", "messages");

function flatten(obj, prefix = "") {
  const out = {};
  for (const [key, value] of Object.entries(obj)) {
    const fullKey = prefix ? `${prefix}.${key}` : key;
    if (value !== null && typeof value === "object" && !Array.isArray(value)) {
      Object.assign(out, flatten(value, fullKey));
    } else {
      out[fullKey] = value;
    }
  }
  return out;
}

function main() {
  const flatByLocale = {};
  let hadError = false;

  for (const locale of LOCALES) {
    const filePath = path.join(MESSAGES_DIR, `${locale}.json`);
    let raw;
    try {
      raw = fs.readFileSync(filePath, "utf8");
    } catch {
      console.error(`[i18n] missing dictionary file: ${filePath}`);
      hadError = true;
      continue;
    }
    let parsed;
    try {
      parsed = JSON.parse(raw);
    } catch (e) {
      console.error(`[i18n] ${locale}.json is not valid JSON: ${e.message}`);
      hadError = true;
      continue;
    }
    const flat = flatten(parsed);
    for (const [key, value] of Object.entries(flat)) {
      if (typeof value !== "string" || value.trim() === "") {
        console.error(`[i18n] ${locale}.json key "${key}" is empty or not a string`);
        hadError = true;
      }
    }
    flatByLocale[locale] = new Set(Object.keys(flat));
  }

  if (hadError) process.exit(1);

  const base = flatByLocale.nl;
  for (const locale of LOCALES) {
    if (locale === "nl") continue;
    const current = flatByLocale[locale];
    const missing = [...base].filter((k) => !current.has(k));
    const extra = [...current].filter((k) => !base.has(k));
    if (missing.length > 0) {
      console.error(`[i18n] ${locale}.json is missing ${missing.length} key(s) present in nl.json:\n  ${missing.join("\n  ")}`);
      hadError = true;
    }
    if (extra.length > 0) {
      console.error(`[i18n] ${locale}.json has ${extra.length} extra key(s) not present in nl.json:\n  ${extra.join("\n  ")}`);
      hadError = true;
    }
  }

  if (hadError) {
    console.error("\n[i18n] translation parity check FAILED");
    process.exit(1);
  }
  console.log(`[i18n] translation parity OK -- ${base.size} keys across ${LOCALES.length} locales`);
}

main();

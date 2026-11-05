#!/usr/bin/env node
// Phase 16.1: deep-merges the parallel translation forks' per-bucket
// fragment files (frontend/.i18n-fragments/bucket*/*.json) into the
// real dictionaries (messages/*.json), reporting any key collision
// across buckets instead of silently letting one overwrite another --
// collisions shouldn't happen if each fork stuck to its assigned
// domain namespace, but this is cheap insurance against two forks
// having added a different value for the same key.
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const MESSAGES_DIR = path.resolve(__dirname, "../messages");
const FRAGMENTS_DIR = path.resolve(__dirname, "../.i18n-fragments");
const LOCALES = ["nl", "en", "fa", "ar"];

function flatten(obj, prefix = "", out = {}) {
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === "object" && !Array.isArray(v)) flatten(v, key, out);
    else out[key] = v;
  }
  return out;
}

function setPath(obj, dottedKey, value) {
  const parts = dottedKey.split(".");
  let node = obj;
  for (let i = 0; i < parts.length - 1; i++) {
    if (typeof node[parts[i]] !== "object" || node[parts[i]] === null) node[parts[i]] = {};
    node = node[parts[i]];
  }
  node[parts[parts.length - 1]] = value;
}

let hadCollision = false;

for (const locale of LOCALES) {
  const realPath = path.join(MESSAGES_DIR, `${locale}.json`);
  const real = JSON.parse(fs.readFileSync(realPath, "utf8"));
  const seenThisRun = new Map(); // dottedKey -> {bucket, value}

  const buckets = fs
    .readdirSync(FRAGMENTS_DIR)
    .filter((d) => fs.statSync(path.join(FRAGMENTS_DIR, d)).isDirectory())
    .sort();

  for (const bucket of buckets) {
    const fragPath = path.join(FRAGMENTS_DIR, bucket, `${locale}.json`);
    if (!fs.existsSync(fragPath)) continue;
    const frag = JSON.parse(fs.readFileSync(fragPath, "utf8"));
    const flat = flatten(frag);
    for (const [key, value] of Object.entries(flat)) {
      if (seenThisRun.has(key)) {
        const prev = seenThisRun.get(key);
        if (prev.value !== value) {
          console.error(
            `[merge-i18n] COLLISION (${locale}) key "${key}": ${prev.bucket}=${JSON.stringify(prev.value)} vs ${bucket}=${JSON.stringify(value)}`
          );
          hadCollision = true;
        }
        continue;
      }
      seenThisRun.set(key, { bucket, value });
      setPath(real, key, value);
    }
  }

  fs.writeFileSync(realPath, JSON.stringify(real, null, 2) + "\n");
  console.log(`[merge-i18n] ${locale}: merged ${seenThisRun.size} keys from ${buckets.length} buckets`);
}

if (hadCollision) {
  console.error("[merge-i18n] FAILED: resolve collisions above before proceeding");
  process.exit(1);
}

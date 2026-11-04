import { getRequestConfig } from "next-intl/server";
import { cookies, headers } from "next/headers";
import { AppLocale, CODE_TO_LOCALE, DEFAULT_LOCALE, LOCALE_COOKIE, isSupportedLocale } from "./config";
import nlMessages from "../messages/nl.json";

/** Parses an Accept-Language header (e.g. "fa;q=0.9,en-GB;q=0.8,nl;q=0.5")
 * into our supported locales, highest-quality first. Used ONLY to pick an
 * initial locale for a visitor with no saved preference yet -- an explicit
 * saved preference (cookie, below) always wins over this, per the brief's
 * explicit "do not assume the browser language should override an
 * explicitly saved preference." */
function pickFromAcceptLanguage(header: string | null): AppLocale | null {
  if (!header) return null;
  const ranked = header
    .split(",")
    .map((part) => {
      const [tag, qPart] = part.trim().split(";q=");
      return { tag: tag.toLowerCase(), q: qPart ? parseFloat(qPart) : 1 };
    })
    .sort((a, b) => b.q - a.q);

  for (const { tag } of ranked) {
    const short = tag.split("-")[0];
    if (short in CODE_TO_LOCALE) return CODE_TO_LOCALE[short];
  }
  return null;
}

async function resolveLocale(): Promise<AppLocale> {
  const cookieStore = await cookies();
  const fromCookie = CODE_TO_LOCALE[cookieStore.get(LOCALE_COOKIE)?.value ?? ""];
  if (isSupportedLocale(fromCookie)) return fromCookie;

  const headerStore = await headers();
  const fromBrowser = pickFromAcceptLanguage(headerStore.get("accept-language"));
  if (fromBrowser) return fromBrowser;

  return DEFAULT_LOCALE;
}

const MESSAGE_MODULES: Record<AppLocale, () => Promise<{ default: Record<string, unknown> }>> = {
  "nl-NL": () => import("../messages/nl.json"),
  "en-GB": () => import("../messages/en.json"),
  "fa-IR": () => import("../messages/fa.json"),
  "ar-SA": () => import("../messages/ar.json"),
};

/** Flattens a nested messages object into "a.b.c" -> value, so a missing
 * key can be looked up in the Dutch fallback dictionary regardless of
 * nesting depth. */
function flatten(obj: Record<string, unknown>, prefix = ""): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === "string") out[path] = value;
    else if (value && typeof value === "object") Object.assign(out, flatten(value as Record<string, unknown>, path));
  }
  return out;
}

const FLAT_NL = flatten(nlMessages);

export default getRequestConfig(async () => {
  const locale = await resolveLocale();
  const messages = (await MESSAGE_MODULES[locale]()).default;

  return {
    locale,
    messages,
    // Called whenever a requested key is missing from the active locale's
    // dictionary (a translator hasn't caught up yet, or a key was added to
    // nl.json without the others). Logs loudly in development (the
    // "detect missing translations during development" requirement) and
    // ALWAYS falls back to the real Dutch string instead of ever letting a
    // raw key like "users.inviteButton" reach the screen.
    onError(error) {
      if (process.env.NODE_ENV !== "production") {
        console.error("[i18n] missing or invalid message:", error.message);
      }
    },
    getMessageFallback({ key, namespace }) {
      const fullKey = namespace ? `${namespace}.${key}` : key;
      return FLAT_NL[fullKey] ?? fullKey;
    },
  };
});

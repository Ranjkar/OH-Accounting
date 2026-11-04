/** Phase 16: the four supported interface languages. Dutch is the
 * default and the ultimate fallback -- every other locale falls back to
 * it (never to a raw translation key) if a message is missing. BCP-47
 * tags are deliberately the full regional form the brief specifies
 * (nl-NL, en-GB, fa-IR, ar-SA), not bare "nl"/"en"/etc, since these also
 * drive Intl.NumberFormat/DateTimeFormat locale-aware formatting. */
export const LOCALES = ["nl-NL", "en-GB", "fa-IR", "ar-SA"] as const;
export type AppLocale = (typeof LOCALES)[number];

export const DEFAULT_LOCALE: AppLocale = "nl-NL";

export const LOCALE_LABELS: Record<AppLocale, string> = {
  "nl-NL": "Nederlands",
  "en-GB": "English",
  "fa-IR": "فارسی",
  "ar-SA": "العربية",
};

/** Short, URL/cookie/backend-safe codes for each locale -- what's
 * actually stored (User.locale, the locale cookie, <select> values).
 * Mapping kept explicit both ways rather than string-slicing, since
 * "nl-NL".slice(0,2) happening to equal the short code is a coincidence
 * of these four locales, not a rule the code should lean on. */
export const LOCALE_TO_CODE: Record<AppLocale, string> = {
  "nl-NL": "nl",
  "en-GB": "en",
  "fa-IR": "fa",
  "ar-SA": "ar",
};
export const CODE_TO_LOCALE: Record<string, AppLocale> = {
  nl: "nl-NL",
  en: "en-GB",
  fa: "fa-IR",
  ar: "ar-SA",
};

export const RTL_LOCALES: ReadonlySet<AppLocale> = new Set(["fa-IR", "ar-SA"]);

export function isRtl(locale: AppLocale): boolean {
  return RTL_LOCALES.has(locale);
}

export function dirFor(locale: AppLocale): "ltr" | "rtl" {
  return isRtl(locale) ? "rtl" : "ltr";
}

export function isSupportedLocale(value: string | undefined | null): value is AppLocale {
  return !!value && (LOCALES as readonly string[]).includes(value);
}

export function isSupportedCode(value: string | undefined | null): value is string {
  return !!value && value in CODE_TO_LOCALE;
}

export const LOCALE_COOKIE = "onholland-locale";

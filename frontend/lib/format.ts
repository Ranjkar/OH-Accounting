/** EUR currency formatting -- the backend returns every monetary value
 * as a plain Decimal string (e.g. "1250.00"), never pre-formatted, so
 * every call site is responsible for presenting it. Centralised here
 * instead of each page reinventing `toLocaleString` with its own
 * options.
 *
 * `locale` only changes digit grouping/decimal-separator presentation
 * (e.g. "€ 1.250,00" in nl-NL vs "€1,250.00" in en-GB) -- the currency
 * itself stays EUR regardless of UI language, per the accounting
 * requirement that money values are language-neutral. Defaults to
 * "nl-NL" so existing call sites that don't pass a locale render
 * exactly as before. */
export function formatEUR(amount: string | number, locale: string = "nl-NL"): string {
  const n = typeof amount === "string" ? Number(amount) : amount;
  if (Number.isNaN(n)) return String(amount);
  return new Intl.NumberFormat(locale, { style: "currency", currency: "EUR" }).format(n);
}

export function formatDate(value: string | Date, locale: string = "nl-NL"): string {
  const d = typeof value === "string" ? new Date(value) : value;
  return new Intl.DateTimeFormat(locale, { day: "2-digit", month: "short", year: "numeric" }).format(d);
}

/** e.g. "21%" / "21,5%" (nl-NL) vs "21.5%" (en-GB) -- VAT rates and
 * other ratios are stored as plain numbers (0.21), never pre-formatted. */
export function formatPercent(value: string | number, locale: string = "nl-NL"): string {
  const n = typeof value === "string" ? Number(value) : value;
  if (Number.isNaN(n)) return String(value);
  return new Intl.NumberFormat(locale, { style: "percent", maximumFractionDigits: 2 }).format(n);
}

/** e.g. "3 days ago" / "in 2 hours" -- for activity feeds and audit logs. */
export function formatRelativeDate(value: string | Date, locale: string = "nl-NL"): string {
  const d = typeof value === "string" ? new Date(value) : value;
  const diffSeconds = (d.getTime() - Date.now()) / 1000;
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ["year", 60 * 60 * 24 * 365],
    ["month", 60 * 60 * 24 * 30],
    ["day", 60 * 60 * 24],
    ["hour", 60 * 60],
    ["minute", 60],
  ];
  for (const [unit, secondsInUnit] of units) {
    if (Math.abs(diffSeconds) >= secondsInUnit) {
      return rtf.format(Math.round(diffSeconds / secondsInUnit), unit);
    }
  }
  return rtf.format(Math.round(diffSeconds), "second");
}

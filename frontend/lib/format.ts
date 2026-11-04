/** Dutch/European currency formatting (e.g. "€ 1.250,00", "-€ 89,50") --
 * the backend returns every monetary value as a plain Decimal string
 * (e.g. "1250.00"), never pre-formatted, so every call site is
 * responsible for presenting it. Centralised here instead of each page
 * reinventing `toLocaleString` with its own options. */
export function formatEUR(amount: string | number): string {
  const n = typeof amount === "string" ? Number(amount) : amount;
  if (Number.isNaN(n)) return String(amount);
  return new Intl.NumberFormat("nl-NL", { style: "currency", currency: "EUR" }).format(n);
}

export function formatDate(value: string | Date): string {
  const d = typeof value === "string" ? new Date(value) : value;
  return new Intl.DateTimeFormat("nl-NL", { day: "2-digit", month: "short", year: "numeric" }).format(d);
}

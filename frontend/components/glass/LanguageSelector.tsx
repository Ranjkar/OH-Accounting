"use client";

import { useTranslations } from "next-intl";
import { LOCALES, LOCALE_LABELS, AppLocale } from "@/i18n/config";
import { useLocalePreference } from "@/lib/locale-context";

/** Mirrors ThemeToggle's segmented-control pattern. A plain <select> would
 * also work, but this keeps every option visible and one click away
 * (same rationale ThemeToggle documents for Light/Dark/System), and the
 * four options here are a similarly short, fixed set. */
export default function LanguageSelector({ compact = false }: { compact?: boolean }) {
  const t = useTranslations("language");
  const { locale, setLocale } = useLocalePreference();

  return (
    <div role="radiogroup" aria-label={t("label")} className="inline-flex flex-wrap items-center gap-0.5 rounded-lg border border-border bg-surface-card p-0.5">
      {LOCALES.map((loc) => (
        <button
          key={loc}
          type="button"
          role="radio"
          aria-checked={locale === loc}
          onClick={() => setLocale(loc)}
          title={LOCALE_LABELS[loc]}
          className={`rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors ${
            locale === loc ? "bg-navy-solid text-white" : "text-text-secondary hover:bg-muted"
          }`}
        >
          {compact ? shortLabel(loc) : LOCALE_LABELS[loc]}
        </button>
      ))}
    </div>
  );
}

function shortLabel(locale: AppLocale): string {
  return locale.slice(0, 2).toUpperCase();
}

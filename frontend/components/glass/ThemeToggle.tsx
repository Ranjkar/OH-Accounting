"use client";

import { useTranslations } from "next-intl";
import { useTheme, ThemePreference } from "@/lib/theme-context";
import { IconSun, IconMoon, IconMonitor } from "./icons";

const OPTIONS: { value: ThemePreference; icon: typeof IconSun }[] = [
  { value: "light", icon: IconSun },
  { value: "dark", icon: IconMoon },
  { value: "system", icon: IconMonitor },
];

/** A 3-way segmented control, not a cycling single button -- all three
 * states (Light/Dark/System) are always visible and one click away,
 * matching the brief's explicit "provide Light, Dark, System options." */
export default function ThemeToggle({ compact = false }: { compact?: boolean }) {
  const { theme, setTheme } = useTheme();
  const t = useTranslations("theme");

  return (
    <div role="radiogroup" aria-label={t("label")} className="inline-flex items-center gap-0.5 rounded-lg border border-border bg-surface-card p-0.5">
      {OPTIONS.map(({ value, icon: Icon }) => (
        <button
          key={value}
          type="button"
          role="radio"
          aria-checked={theme === value}
          onClick={() => setTheme(value)}
          title={t(value)}
          className={`flex items-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-medium transition-colors ${
            theme === value ? "bg-navy-solid text-white" : "text-text-secondary hover:bg-muted"
          }`}
        >
          <Icon size={14} />
          {!compact && <span>{t(value)}</span>}
        </button>
      ))}
    </div>
  );
}

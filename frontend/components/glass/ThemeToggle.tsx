"use client";

import { useTheme, ThemePreference } from "@/lib/theme-context";
import { IconSun, IconMoon, IconMonitor } from "./icons";

const OPTIONS: { value: ThemePreference; label: string; icon: typeof IconSun }[] = [
  { value: "light", label: "Light", icon: IconSun },
  { value: "dark", label: "Dark", icon: IconMoon },
  { value: "system", label: "System", icon: IconMonitor },
];

/** A 3-way segmented control, not a cycling single button -- all three
 * states (Light/Dark/System) are always visible and one click away,
 * matching the brief's explicit "provide Light, Dark, System options." */
export default function ThemeToggle({ compact = false }: { compact?: boolean }) {
  const { theme, setTheme } = useTheme();

  return (
    <div role="radiogroup" aria-label="Colour theme" className="inline-flex items-center gap-0.5 rounded-lg border border-border bg-surface-card p-0.5">
      {OPTIONS.map(({ value, label, icon: Icon }) => (
        <button
          key={value}
          type="button"
          role="radio"
          aria-checked={theme === value}
          onClick={() => setTheme(value)}
          title={label}
          className={`flex items-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-medium transition-colors ${
            theme === value ? "bg-navy-solid text-white" : "text-text-secondary hover:bg-muted"
          }`}
        >
          <Icon size={14} />
          {!compact && <span>{label}</span>}
        </button>
      ))}
    </div>
  );
}

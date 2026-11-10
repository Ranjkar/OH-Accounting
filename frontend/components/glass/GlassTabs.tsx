"use client";

interface GlassTabsProps<T extends string> {
  tabs: { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
}

export default function GlassTabs<T extends string>({ tabs, value, onChange }: GlassTabsProps<T>) {
  return (
    <div role="tablist" className="inline-flex items-center gap-1 glass-panel p-1">
      {tabs.map((tab) => (
        <button
          key={tab.value}
          role="tab"
          aria-selected={value === tab.value}
          onClick={() => onChange(tab.value)}
          className={`pill-v2 px-3 py-1.5 text-sm font-medium transition-colors ${
            value === tab.value ? "btn-primary-v2" : "text-text-secondary hover:text-text-primary"
          }`}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

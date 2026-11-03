"use client";

import { useRouter } from "next/navigation";
import { useMemo, useRef, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { IconSearch } from "./icons";
import { EMPLOYEE_ROLE_NAV_GROUPS, NAV_GROUPS } from "./navConfig";

/** Real functionality, not a decorative input: filters this app's own
 * navigation destinations client-side (no fake search index, no server
 * call pretending to search content that isn't indexed anywhere). */
export default function GlassNavSearch() {
  const { user } = useAuth();
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [focused, setFocused] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const groups = user?.role === "employee" ? EMPLOYEE_ROLE_NAV_GROUPS : NAV_GROUPS;
  const allItems = useMemo(() => groups.flatMap((g) => g.items.filter((i) => i.href).map((i) => ({ ...i, group: g.label }))), [groups]);

  const matches = query.trim()
    ? allItems.filter((i) => i.label.toLowerCase().includes(query.trim().toLowerCase())).slice(0, 8)
    : [];

  function go(href: string) {
    router.push(href);
    setQuery("");
    setFocused(false);
    inputRef.current?.blur();
  }

  return (
    <div className="relative w-full">
      <IconSearch size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-secondary" />
      <input
        ref={inputRef}
        type="search"
        placeholder="Search pages..."
        aria-label="Search pages"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onFocus={() => setFocused(true)}
        onBlur={() => setTimeout(() => setFocused(false), 120)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && matches[0]) go(matches[0].href!);
          if (e.key === "Escape") setQuery("");
        }}
        className="input-v2 w-full pl-9 pr-3 py-2 text-sm"
      />
      {focused && matches.length > 0 && (
        <div role="listbox" className="absolute left-0 right-0 mt-1.5 glass-panel p-1.5 z-40">
          {matches.map((m) => (
            <button
              key={m.href}
              role="option"
              aria-selected={false}
              onMouseDown={() => go(m.href!)}
              className="w-full text-left px-3 py-2 rounded-lg text-sm hover:bg-white/60 flex items-center justify-between gap-2"
            >
              <span className="text-text-primary">{m.label}</span>
              <span className="text-xs text-text-secondary">{m.group}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

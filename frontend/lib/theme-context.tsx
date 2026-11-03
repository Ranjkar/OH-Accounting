"use client";

import { createContext, useContext, useEffect, useState, ReactNode } from "react";

export type ThemePreference = "light" | "dark" | "system";
type ResolvedTheme = "light" | "dark";

const STORAGE_KEY = "onholland-theme";

function systemPrefersDark(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function resolve(pref: ThemePreference): ResolvedTheme {
  return pref === "system" ? (systemPrefersDark() ? "dark" : "light") : pref;
}

interface ThemeState {
  theme: ThemePreference;
  resolvedTheme: ResolvedTheme;
  setTheme: (t: ThemePreference) => void;
}

const ThemeContext = createContext<ThemeState | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  // Read synchronously so the very first render already matches whatever
  // the anti-flash inline script (see app/layout.tsx) wrote to
  // documentElement before paint -- this value is never wrong on first
  // render, so no flash-of-wrong-theme on hydration either.
  const [theme, setThemeState] = useState<ThemePreference>(() => {
    if (typeof window === "undefined") return "system";
    try {
      return (localStorage.getItem(STORAGE_KEY) as ThemePreference) || "system";
    } catch {
      return "system";
    }
  });
  const [resolvedTheme, setResolvedTheme] = useState<ResolvedTheme>(() => resolve(theme));

  function apply(pref: ThemePreference) {
    const resolved = resolve(pref);
    setResolvedTheme(resolved);
    document.documentElement.setAttribute("data-theme", resolved);
  }

  function setTheme(pref: ThemePreference) {
    setThemeState(pref);
    try {
      localStorage.setItem(STORAGE_KEY, pref);
    } catch {
      // Private-browsing/blocked storage -- preference still applies for this session.
    }
    apply(pref);
  }

  useEffect(() => {
    // Re-applying (and re-resolving "system") on every theme change --
    // syncing to an external system (the DOM attribute + OS preference),
    // not state derivable during render.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    apply(theme);
    if (theme !== "system") return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => apply("system");
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [theme]);

  return <ThemeContext.Provider value={{ theme, resolvedTheme, setTheme }}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}

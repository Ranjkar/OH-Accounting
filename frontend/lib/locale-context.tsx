"use client";

import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { NextIntlClientProvider } from "next-intl";
import {
  AppLocale,
  CODE_TO_LOCALE,
  LOCALE_COOKIE,
  LOCALE_TO_CODE,
  dirFor,
  isSupportedCode,
} from "@/i18n/config";
import { useAuth } from "./auth-context";
import { api } from "./api";

// Statically imported (not dynamic `import()`) so a language switch is a
// synchronous in-memory swap, not a network fetch -- all four dictionaries
// together are small (see messages/__tests__/parity.test.ts), and this
// sidesteps any bundler-specific behaviour around dynamic import() with a
// template-literal path.
import nlMessages from "@/messages/nl.json";
import enMessages from "@/messages/en.json";
import faMessages from "@/messages/fa.json";
import arMessages from "@/messages/ar.json";

type Messages = typeof nlMessages;

const MESSAGES_BY_LOCALE: Record<AppLocale, Messages> = {
  "nl-NL": nlMessages,
  "en-GB": enMessages,
  "fa-IR": faMessages,
  "ar-SA": arMessages,
};

interface LocaleState {
  locale: AppLocale;
  setLocale: (locale: AppLocale) => void;
}

const LocaleContext = createContext<LocaleState | null>(null);

function applyDocumentAttrs(locale: AppLocale) {
  document.documentElement.setAttribute("lang", locale);
  document.documentElement.setAttribute("dir", dirFor(locale));
}

function persistLocally(locale: AppLocale) {
  const code = LOCALE_TO_CODE[locale];
  try {
    document.cookie = `${LOCALE_COOKIE}=${code}; path=/; max-age=31536000; samesite=lax`;
    localStorage.setItem(LOCALE_COOKIE, code);
  } catch {
    // Private browsing / blocked storage -- the preference still applies
    // for this tab via React state, just won't survive a reload.
  }
}

export function LocaleProvider({ initialLocale, children }: { initialLocale: AppLocale; children: ReactNode }) {
  const { user, token } = useAuth();
  // Read synchronously so first client render matches what the server
  // already decided (cookie-resolved in i18n/request.ts) -- same
  // no-mismatch-on-hydration principle as ThemeProvider.
  const [locale, setLocaleState] = useState<AppLocale>(initialLocale);
  const [syncedFromBackend, setSyncedFromBackend] = useState(false);

  function setLocale(next: AppLocale, persistToBackend = true) {
    setLocaleState(next);
    applyDocumentAttrs(next);
    persistLocally(next);
    if (persistToBackend && token) {
      api.updateMyLocale(token, LOCALE_TO_CODE[next]).catch(() => {
        // Non-fatal -- the choice still applies locally via the cookie;
        // it just won't have followed to other devices this time.
      });
    }
  }

  useEffect(() => {
    // Keep documentElement in sync even if locale was set before this
    // effect's first run (covers the initial mount).
    applyDocumentAttrs(locale);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Once per authenticated session: if the backend has an explicit
  // preference (or tenant default) that differs from what's currently
  // showing, adopt it -- this is what makes the preference "follow the
  // user across devices after logging in." Deliberately only syncs once
  // (guarded by syncedFromBackend) so it can never fight a locale the
  // user picks by hand later in the same session, and never overrides an
  // explicit choice already reflected in this browser's own cookie.
  useEffect(() => {
    if (!user || syncedFromBackend) return;
    const backendCode = user.locale ?? user.tenant_default_locale;
    if (isSupportedCode(backendCode)) {
      const backendLocale = CODE_TO_LOCALE[backendCode];
      if (backendLocale !== locale) {
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setLocale(backendLocale, false);
      }
    }
    setSyncedFromBackend(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, syncedFromBackend]);

  return (
    <LocaleContext.Provider value={{ locale, setLocale }}>
      <NextIntlClientProvider locale={locale} messages={MESSAGES_BY_LOCALE[locale]} timeZone="Europe/Amsterdam">
        {children}
      </NextIntlClientProvider>
    </LocaleContext.Provider>
  );
}

/** Named deliberately differently from next-intl's own `useLocale()` (which
 * only reads the active locale, no setter) to avoid import confusion --
 * components that need to read-only are expected to import next-intl's. */
export function useLocalePreference() {
  const ctx = useContext(LocaleContext);
  if (!ctx) throw new Error("useLocalePreference must be used within LocaleProvider");
  return ctx;
}

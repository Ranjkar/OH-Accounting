import type { AppLocale } from "@/i18n/config";
import type nlMessages from "./messages/nl.json";

/** Typed translation keys (Phase 16): augments next-intl's own types so
 * `useTranslations("dashboard")` autocompletes real keys and a typo like
 * `t("dashbord.title")` is a compile error, not a silent runtime
 * fallback. nl.json is the source of truth for the key *shape* -- every
 * other dictionary is checked against it for parity at test time
 * (messages/__tests__/parity.test.ts), not by this type (TypeScript
 * can't type-check JSON file contents against each other). */
declare module "next-intl" {
  interface AppConfig {
    Locale: AppLocale;
    Messages: typeof nlMessages;
  }
}

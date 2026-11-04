import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { LocaleProvider, useLocalePreference } from "../locale-context";

const mockUpdateMyLocale = vi.fn().mockResolvedValue(undefined);
let mockUser: { locale: string | null; tenant_default_locale: string } | null = null;

vi.mock("../auth-context", () => ({
  useAuth: () => ({ user: mockUser, token: "fake-token" }),
}));

vi.mock("../api", () => ({
  api: { updateMyLocale: (...args: unknown[]) => mockUpdateMyLocale(...args) },
}));

function Probe() {
  const { locale } = useLocalePreference();
  return <span data-testid="locale">{locale}</span>;
}

/** Regression test for a real bug found during Phase 16 Playwright
 * verification: logging in reverted the interface to Dutch for every
 * non-Dutch locale, even when the user had deliberately switched
 * language (via the cookie) before logging in. Root cause: the
 * "sync preference from the backend once per session" effect treated
 * `user.tenant_default_locale` (a generic, never-personally-chosen
 * fallback -- "nl" for every pre-Phase-16 tenant) as if it were an
 * explicit saved preference, and overwrote the browser's current
 * locale with it. */
describe("LocaleProvider backend sync", () => {
  afterEach(() => {
    cleanup();
    mockUpdateMyLocale.mockClear();
    mockUser = null;
  });

  it("does NOT overwrite the current locale with the tenant default when the user has no personal override", async () => {
    mockUser = { locale: null, tenant_default_locale: "nl" };
    render(
      <LocaleProvider initialLocale="ar-SA">
        <Probe />
      </LocaleProvider>
    );
    expect(await screen.findByTestId("locale")).toHaveTextContent("ar-SA");
  });

  it("persists the current (locally-chosen) locale to the backend when the user had no override saved", async () => {
    mockUser = { locale: null, tenant_default_locale: "nl" };
    render(
      <LocaleProvider initialLocale="fa-IR">
        <Probe />
      </LocaleProvider>
    );
    await screen.findByTestId("locale");
    expect(mockUpdateMyLocale).toHaveBeenCalledWith("fake-token", "fa");
  });

  it("DOES adopt an explicit personal override that differs from the current locale", async () => {
    mockUser = { locale: "ar", tenant_default_locale: "nl" };
    render(
      <LocaleProvider initialLocale="nl-NL">
        <Probe />
      </LocaleProvider>
    );
    expect(await screen.findByTestId("locale")).toHaveTextContent("ar-SA");
  });

  it("does nothing when the explicit personal override already matches the current locale", async () => {
    mockUser = { locale: "en", tenant_default_locale: "nl" };
    render(
      <LocaleProvider initialLocale="en-GB">
        <Probe />
      </LocaleProvider>
    );
    await screen.findByTestId("locale");
    expect(screen.getByTestId("locale")).toHaveTextContent("en-GB");
    expect(mockUpdateMyLocale).not.toHaveBeenCalled();
  });
});

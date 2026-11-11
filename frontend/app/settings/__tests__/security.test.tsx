import { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import enMessages from "../../../messages/en.json";
import { api, User } from "@/lib/api";
import SettingsPage from "../page";

const rotateToken = vi.fn();
const refreshUser = vi.fn();
let authUser: User | null = null;

vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({ token: "test-token", user: authUser, login: vi.fn(), logout: vi.fn(), refreshUser, rotateToken }),
}));
vi.mock("@/components/AuthGuard", () => ({ default: ({ children }: { children: ReactNode }) => <>{children}</> }));
vi.mock("@/components/Shell", () => ({ default: ({ children }: { children: ReactNode }) => <>{children}</> }));
// Provider-bound controls that this suite does not exercise.
vi.mock("@/components/glass/ThemeToggle", () => ({ default: () => null }));
vi.mock("@/components/glass/LanguageSelector", () => ({ default: () => null }));

function baseUser(overrides: Partial<User> = {}): User {
  return {
    id: 1, email: "visser@voorbeeld.nl", full_name: "A. Visser", role: "admin", is_platform_admin: false,
    mfa_enabled: false, is_active: true, tenant_id: 2, locale: "nl", tenant_default_locale: "nl",
    first_name: "Anne", last_name: "Visser", display_name: null, phone: null,
    address_line: null, postal_code: null, city: null, country: null, pending_email: null,
    ...overrides,
  } as User;
}

function renderSettings() {
  return render(
    <NextIntlClientProvider locale="en-GB" messages={enMessages} timeZone="Europe/Amsterdam">
      <SettingsPage />
    </NextIntlClientProvider>
  );
}

describe("settings: profile and account security", () => {
  beforeEach(() => {
    authUser = baseUser();
    rotateToken.mockReset();
    refreshUser.mockReset().mockResolvedValue(undefined);
    vi.spyOn(api, "listCompanies").mockResolvedValue([]);
    vi.spyOn(api, "updateMyProfile").mockResolvedValue(baseUser({ first_name: "Anna" }));
    vi.spyOn(api, "changeMyPassword").mockResolvedValue({ access_token: "rotated-token" });
    vi.spyOn(api, "requestEmailChange").mockResolvedValue(baseUser({ pending_email: "nieuw@voorbeeld.nl" }));
    vi.spyOn(api, "cancelEmailChange").mockResolvedValue(baseUser());
    vi.spyOn(api, "revokeOtherSessions").mockResolvedValue({ access_token: "rotated-token" });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("saves the profile with empty fields sent as null", async () => {
    renderSettings();
    const firstName = await screen.findByLabelText("First name");
    fireEvent.change(firstName, { target: { value: "Anna" } });
    fireEvent.change(screen.getByLabelText("Country (2 letters)"), { target: { value: "nl" } });
    fireEvent.click(screen.getByRole("button", { name: "Save profile" }));
    await waitFor(() =>
      expect(api.updateMyProfile).toHaveBeenCalledWith(
        "test-token",
        expect.objectContaining({ first_name: "Anna", country: "NL", display_name: null, phone: null })
      )
    );
    expect(await screen.findByText("Profile saved.")).toBeInTheDocument();
  });

  it("blocks a password change whose confirmation differs, without calling the API", async () => {
    renderSettings();
    await screen.findAllByLabelText("Current password");
    fireEvent.change(screen.getAllByLabelText("Current password")[0], { target: { value: "Oud-Wachtwoord-1" } });
    fireEvent.change(screen.getByLabelText("New password"), { target: { value: "Nieuw-Wachtwoord-1" } });
    fireEvent.change(screen.getByLabelText("Confirm new password"), { target: { value: "Nieuw-Wachtwoord-2" } });
    fireEvent.click(screen.getByRole("button", { name: "Change password" }));
    expect(await screen.findByText("New password and confirmation do not match.")).toBeInTheDocument();
    expect(api.changeMyPassword).not.toHaveBeenCalled();
  });

  it("enforces the server's password policy locally", async () => {
    renderSettings();
    await screen.findAllByLabelText("Current password");
    fireEvent.change(screen.getAllByLabelText("Current password")[0], { target: { value: "Oud-Wachtwoord-1" } });
    fireEvent.change(screen.getByLabelText("New password"), { target: { value: "kort1" } });
    fireEvent.change(screen.getByLabelText("Confirm new password"), { target: { value: "kort1" } });
    fireEvent.click(screen.getByRole("button", { name: "Change password" }));
    expect(await screen.findByText("Use at least 10 characters.")).toBeInTheDocument();
    expect(api.changeMyPassword).not.toHaveBeenCalled();
  });

  it("rotates the stored token after a password change, so this device stays signed in", async () => {
    renderSettings();
    await screen.findAllByLabelText("Current password");
    fireEvent.change(screen.getAllByLabelText("Current password")[0], { target: { value: "Oud-Wachtwoord-1" } });
    fireEvent.change(screen.getByLabelText("New password"), { target: { value: "Nieuw-Wachtwoord-1" } });
    fireEvent.change(screen.getByLabelText("Confirm new password"), { target: { value: "Nieuw-Wachtwoord-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Change password" }));
    await waitFor(() => expect(api.changeMyPassword).toHaveBeenCalledWith("test-token", "Oud-Wachtwoord-1", "Nieuw-Wachtwoord-1", "Nieuw-Wachtwoord-1"));
    expect(rotateToken).toHaveBeenCalledWith("rotated-token");
    expect(await screen.findByText("Password changed. Other devices were signed out.")).toBeInTheDocument();
  });

  it("shows the pending email change with a way to cancel it", async () => {
    authUser = baseUser({ pending_email: "nieuw@voorbeeld.nl" });
    renderSettings();
    expect(await screen.findByText("Verification link sent to nieuw@voorbeeld.nl. Your sign-in address changes once you open that link.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cancel change" }));
    await waitFor(() => expect(api.cancelEmailChange).toHaveBeenCalledWith("test-token"));
  });

  it("requests an email change with password re-authentication", async () => {
    renderSettings();
    await screen.findByLabelText("New email address");
    fireEvent.change(screen.getByLabelText("New email address"), { target: { value: "nieuw@voorbeeld.nl" } });
    fireEvent.change(screen.getAllByLabelText("Current password")[1], { target: { value: "Wachtwoord-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Request change" }));
    await waitFor(() => expect(api.requestEmailChange).toHaveBeenCalledWith("test-token", "nieuw@voorbeeld.nl", "Wachtwoord-1"));
  });

  it("asks before revoking other sessions, then rotates the token", async () => {
    renderSettings();
    fireEvent.click(await screen.findByRole("button", { name: "Sign out everywhere else" }));
    expect(screen.getByText("Sign out every other device now?")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Sign out everywhere else" }));
    await waitFor(() => expect(api.revokeOtherSessions).toHaveBeenCalledWith("test-token"));
    expect(rotateToken).toHaveBeenCalledWith("rotated-token");
    expect(await screen.findByText("All other sessions were ended.")).toBeInTheDocument();
  });
});

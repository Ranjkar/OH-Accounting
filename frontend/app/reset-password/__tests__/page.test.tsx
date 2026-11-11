import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import enMessages from "../../../messages/en.json";
import { api } from "@/lib/api";
import ResetPasswordPage from "../page";

const searchState = { token: null as string | null };

vi.mock("next/navigation", () => ({
  useSearchParams: () => ({ get: (key: string) => (key === "token" ? searchState.token : null) }),
}));

function renderPage() {
  return render(
    <NextIntlClientProvider locale="en-GB" messages={enMessages} timeZone="Europe/Amsterdam">
      <ResetPasswordPage />
    </NextIntlClientProvider>
  );
}

describe("reset password page", () => {
  beforeEach(() => {
    searchState.token = null;
    vi.spyOn(api, "requestPasswordReset").mockResolvedValue(undefined);
    vi.spyOn(api, "confirmPasswordReset").mockResolvedValue(undefined);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("requests a reset link and answers neutrally about unknown addresses", async () => {
    renderPage();
    fireEvent.change(await screen.findByLabelText("Email address"), { target: { value: "onbekend@voorbeeld.nl" } });
    fireEvent.click(screen.getByRole("button", { name: "Send link" }));
    await waitFor(() => expect(api.requestPasswordReset).toHaveBeenCalledWith("onbekend@voorbeeld.nl"));
    expect(
      await screen.findByText("If an account exists for that address, a reset link is on its way. The link expires after a while.")
    ).toBeInTheDocument();
  });

  it("with a token, blocks a confirmation mismatch before calling the API", async () => {
    searchState.token = "reset-token";
    renderPage();
    fireEvent.change(await screen.findByLabelText("New password"), { target: { value: "Nieuw-Wachtwoord-1" } });
    fireEvent.change(screen.getByLabelText("Confirm new password"), { target: { value: "Nieuw-Wachtwoord-2" } });
    fireEvent.click(screen.getByRole("button", { name: "Set password" }));
    expect(await screen.findByText("Password and confirmation do not match.")).toBeInTheDocument();
    expect(api.confirmPasswordReset).not.toHaveBeenCalled();
  });

  it("with a token, applies the password policy locally", async () => {
    searchState.token = "reset-token";
    renderPage();
    fireEvent.change(await screen.findByLabelText("New password"), { target: { value: "abc" } });
    fireEvent.change(screen.getByLabelText("Confirm new password"), { target: { value: "abc" } });
    fireEvent.click(screen.getByRole("button", { name: "Set password" }));
    expect(await screen.findByText("Use at least 10 characters.")).toBeInTheDocument();
    expect(api.confirmPasswordReset).not.toHaveBeenCalled();
  });

  it("with a token, sets the new password and offers the way back to login", async () => {
    searchState.token = "reset-token";
    renderPage();
    fireEvent.change(await screen.findByLabelText("New password"), { target: { value: "Nieuw-Wachtwoord-1" } });
    fireEvent.change(screen.getByLabelText("Confirm new password"), { target: { value: "Nieuw-Wachtwoord-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Set password" }));
    await waitFor(() => expect(api.confirmPasswordReset).toHaveBeenCalledWith("reset-token", "Nieuw-Wachtwoord-1"));
    expect(await screen.findByText("Your password is set. Sign in with your new password.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to sign in" })).toBeInTheDocument();
  });
});

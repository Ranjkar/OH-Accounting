import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import enMessages from "../../../messages/en.json";
import { api, ApiError } from "@/lib/api";
import VerifyEmailPage from "../page";

const searchState = { token: null as string | null };

vi.mock("next/navigation", () => ({
  useSearchParams: () => ({ get: (key: string) => (key === "token" ? searchState.token : null) }),
}));

function renderPage() {
  return render(
    <NextIntlClientProvider locale="en-GB" messages={enMessages} timeZone="Europe/Amsterdam">
      <VerifyEmailPage />
    </NextIntlClientProvider>
  );
}

describe("verify email page", () => {
  beforeEach(() => {
    searchState.token = "verify-token";
    vi.spyOn(api, "confirmEmailChange").mockResolvedValue(undefined);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("confirms the change from the link and reports success", async () => {
    renderPage();
    expect(await screen.findByText("Your email address is confirmed. Sign in with your new address.")).toBeInTheDocument();
    expect(api.confirmEmailChange).toHaveBeenCalledWith("verify-token");
  });

  it("spends the single-use token once, even under StrictMode", async () => {
    render(
      <StrictMode>
        <NextIntlClientProvider locale="en-GB" messages={enMessages} timeZone="Europe/Amsterdam">
          <VerifyEmailPage />
        </NextIntlClientProvider>
      </StrictMode>
    );
    expect(await screen.findByText("Your email address is confirmed. Sign in with your new address.")).toBeInTheDocument();
    expect(api.confirmEmailChange).toHaveBeenCalledTimes(1);
  });

  it("reports an invalid or expired link", async () => {
    vi.mocked(api.confirmEmailChange).mockRejectedValue(new ApiError(400, "Invalid or expired verification link"));
    renderPage();
    expect(await screen.findByText("Invalid or expired verification link")).toBeInTheDocument();
  });

  it("without a token, explains instead of calling the API", async () => {
    searchState.token = null;
    renderPage();
    expect(await screen.findByText("This link does not contain a verification token.")).toBeInTheDocument();
    expect(api.confirmEmailChange).not.toHaveBeenCalled();
  });
});

import { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import enMessages from "../../../messages/en.json";
import { api, BankAccount } from "@/lib/api";
import BankingPage from "../page";

vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({
    token: "test-token",
    user: { id: 1, email: "a@b.nl", full_name: "A", role: "admin", is_platform_admin: false, mfa_enabled: false },
    login: vi.fn(),
    logout: vi.fn(),
    refreshUser: vi.fn(),
    rotateToken: vi.fn(),
  }),
}));
vi.mock("@/components/AuthGuard", () => ({ default: ({ children }: { children: ReactNode }) => <>{children}</> }));
vi.mock("@/components/Shell", () => ({ default: ({ children }: { children: ReactNode }) => <>{children}</> }));
vi.mock("@/lib/navigation", () => ({ navigateAway: vi.fn() }));

function account(overrides: Partial<BankAccount> = {}): BankAccount {
  return {
    id: 5, company_id: 1, iban: "NL91ABNA0417164300", account_name: "Main", currency: "EUR",
    consent_status: "NOT_CONNECTED", provider_name: null, consent_granted_at: null, consent_expires_at: null,
    last_synced_at: null, last_sync_error: null, pending_provider_accounts: null, created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

import { navigateAway } from "@/lib/navigation";


function renderPage() {
  return render(
    <NextIntlClientProvider locale="en-GB" messages={enMessages} timeZone="Europe/Amsterdam">
      <BankingPage />
    </NextIntlClientProvider>
  );
}

describe("bank connection wizard", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "/banking");
    vi.spyOn(api, "listCompanies").mockResolvedValue([{ id: 1, name: "Test B.V." } as never]);
    vi.spyOn(api, "listBankAccounts").mockResolvedValue([account()]);
    vi.spyOn(api, "listImportBatches").mockResolvedValue([]);
    vi.spyOn(api, "openBankingStatus").mockResolvedValue({ provider: "stub", is_sandbox: true, live_connectivity: false });
    vi.spyOn(api, "listBanks").mockResolvedValue({
      provider: "stub", is_sandbox: true, live_connectivity: false,
      banks: [
        { id: "ing", name: "ING", bic: "INGBNL2A", available: true, sandbox: true },
        { id: "rabobank", name: "Rabobank", bic: "RABONL2U", available: true, sandbox: true },
      ],
    });
    vi.spyOn(api, "connectOpenBanking").mockResolvedValue({ authorization_url: "https://bank.example/consent?x=1", provider: "stub", is_sandbox: true });
    vi.spyOn(api, "completeOpenBanking").mockResolvedValue({ account: account({ consent_status: "CONNECTED" }), candidates: [] });
    vi.spyOn(api, "selectOpenBankingAccount").mockResolvedValue(account({ consent_status: "CONNECTED" }));
    vi.spyOn(api, "syncOpenBanking").mockResolvedValue({ id: 1, transaction_count: 0, duplicate_count: 0, error_count: 0 } as never);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("warns that the sandbox provider is synthetic before any consent", async () => {
    renderPage();
    expect(await screen.findByText("Sandbox provider active: connections use synthetic test data, never a real bank.")).toBeInTheDocument();
  });

  it("offers a searchable bank picker and starts consent with a same-origin redirect", async () => {
    renderPage();
    // Select the account row first.
    fireEvent.click((await screen.findAllByRole("button", { name: "Select" }))[0]);
    fireEvent.click(await screen.findByRole("button", { name: "Connect" }));
    expect(await screen.findByLabelText("Choose your bank")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Choose your bank"), { target: { value: "ing" } });
    await waitFor(() => expect(api.listBanks).toHaveBeenCalledWith("test-token", "ing"));
    fireEvent.click(screen.getByRole("button", { name: /ING/ }));
    await waitFor(() =>
      expect(api.connectOpenBanking).toHaveBeenCalledWith("test-token", 5, "http://localhost:3000/banking?ob_account=5", "ing")
    );
    expect(navigateAway).toHaveBeenCalledWith("https://bank.example/consent?x=1");
  });

  it("finishes the consent from the redirect and asks which account when several match", async () => {
    window.history.replaceState(null, "", "/banking?ob_account=5&stub_consent_id=stub-consent-1");
    vi.mocked(api.completeOpenBanking).mockResolvedValue({
      account: account({ consent_status: "PENDING" }),
      candidates: [
        { provider_account_id: "stub-acct-1", iban_masked: "NL00STUB0123456789", account_name: "Stub Business", currency: "EUR" },
        { provider_account_id: "stub-acct-2", iban_masked: "NL00STUB0987654321", account_name: "Stub Savings", currency: "EUR" },
      ],
    });
    renderPage();
    expect((await screen.findAllByText("Your consent covers several accounts. Choose which one this connection is for.")).length).toBeGreaterThan(0);
    await waitFor(() =>
      expect(api.completeOpenBanking).toHaveBeenCalledWith("test-token", 5, expect.objectContaining({ stub_consent_id: "stub-consent-1" }))
    );
    // The one-time callback params are stripped from the address bar.
    expect(window.location.search).toBe("");

    const card = screen.getByRole("button", { name: "Use this account" }).closest("div.space-y-2.rounded-md") as HTMLElement;
    fireEvent.click(within(card).getAllByRole("radio")[1]);
    fireEvent.click(screen.getByRole("button", { name: "Use this account" }));
    await waitFor(() => expect(api.selectOpenBankingAccount).toHaveBeenCalledWith("test-token", 5, "stub-acct-2"));
    expect(await screen.findByText("Bank connection established.")).toBeInTheDocument();
  });

  it("shows the consent expiry for a connected account", async () => {
    vi.spyOn(api, "listBankAccounts").mockResolvedValue([account({ consent_status: "CONNECTED", provider_name: "stub", consent_expires_at: "2027-02-01T00:00:00Z" })]);
    renderPage();
    fireEvent.click((await screen.findAllByRole("button", { name: "Select" }))[0]);
    expect(await screen.findByText(/Consent valid until/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Sync now" }));
    await waitFor(() => expect(api.syncOpenBanking).toHaveBeenCalledWith("test-token", 5));
  });
});

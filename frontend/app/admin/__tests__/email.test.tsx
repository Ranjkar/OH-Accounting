import { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import enMessages from "../../../messages/en.json";
import { api, EmailOutboxEntry, EmailStatus, User } from "@/lib/api";
import EmailAdminPage from "../email/page";

let platformAdmin = true;

vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({
    token: "test-token",
    user: { id: 1, email: "root@onholland.nl", full_name: "Root", role: "owner", is_platform_admin: platformAdmin, mfa_enabled: false } as User,
    login: vi.fn(),
    logout: vi.fn(),
    refreshUser: vi.fn(),
    rotateToken: vi.fn(),
  }),
}));
vi.mock("@/components/AuthGuard", () => ({ default: ({ children }: { children: ReactNode }) => <>{children}</> }));
vi.mock("@/components/Shell", () => ({ default: ({ children }: { children: ReactNode }) => <>{children}</> }));

const STATUS: EmailStatus = {
  provider: "none",
  configured: false,
  missing_settings: ["EMAIL_PROVIDER"],
  from_address: "no-reply@localhost",
  from_name: "OnHolland Accounting",
  app_base_url: "http://localhost:3000",
  smtp_host: null,
  smtp_port: null,
  smtp_security: null,
  rate_limits: { per_recipient_per_hour: 10, per_tenant_per_hour: 200 },
  last_24h: { sent: 3, failed: 1, queued: 0 },
  dns: { domain: "localhost", spf: "localhost TXT v=spf1", dkim: "provider selectors", dmarc: "_dmarc.localhost TXT v=DMARC1" },
};

function outboxRow(overrides: Partial<EmailOutboxEntry> = {}): EmailOutboxEntry {
  return {
    id: 1, tenant_id: null, to_email: "someone@example.com", template: "test", subject: "Test", locale: "nl",
    status: "failed", attempts: 3, last_error: "connection refused", provider_name: null, provider_message_id: null,
    created_at: "2026-11-11T10:00:00Z", sent_at: null,
    ...overrides,
  };
}

function renderPage() {
  return render(
    <NextIntlClientProvider locale="en-GB" messages={enMessages} timeZone="Europe/Amsterdam">
      <EmailAdminPage />
    </NextIntlClientProvider>
  );
}

describe("email administration", () => {
  beforeEach(() => {
    platformAdmin = true;
    vi.spyOn(api, "emailStatus").mockResolvedValue(STATUS);
    vi.spyOn(api, "emailOutbox").mockResolvedValue([
      outboxRow({ id: 1, status: "failed", template: "test" }),
      outboxRow({ id: 2, status: "failed", template: "password_reset", last_error: "smtp timeout" }),
      outboxRow({ id: 3, status: "sent", template: "invitation" }),
    ]);
    vi.spyOn(api, "sendTestEmail").mockResolvedValue(outboxRow({ id: 9, status: "queued" }));
    vi.spyOn(api, "retryEmail").mockResolvedValue(outboxRow({ id: 1, status: "sent" }));
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("shows the provider status and what is missing", async () => {
    renderPage();
    expect(await screen.findByText("Provider not configured")).toBeInTheDocument();
    expect(screen.getByText("EMAIL_PROVIDER")).toBeInTheDocument();
    expect(screen.getAllByText("none").length).toBeGreaterThan(0);
  });

  it("offers retry only for failed TEST messages", async () => {
    renderPage();
    await screen.findByText("Delivery log");
    // GlassTable renders a desktop table and mobile cards; scope to the table.
    const retries = within(await screen.findByRole("table")).getAllByRole("button", { name: "Retry" });
    expect(retries).toHaveLength(1);
    fireEvent.click(retries[0]);
    await waitFor(() => expect(api.retryEmail).toHaveBeenCalledWith("test-token", 1));
    // The one-time-link row explains itself instead of offering a retry.
    expect(screen.getAllByText("smtp timeout").length).toBeGreaterThan(0);
  });

  it("sends a test message to a named recipient", async () => {
    renderPage();
    await screen.findByLabelText("Recipient (empty = your own address)");
    fireEvent.change(screen.getByLabelText("Recipient (empty = your own address)"), { target: { value: "qa@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: "Send test" }));
    await waitFor(() => expect(api.sendTestEmail).toHaveBeenCalledWith("test-token", "qa@example.com"));
    expect(await screen.findByText('Test message queued with status "queued".')).toBeInTheDocument();
  });

  it("filters the outbox by status", async () => {
    renderPage();
    await screen.findByText("Delivery log");
    fireEvent.change(screen.getByLabelText("Filter by status"), { target: { value: "failed" } });
    await waitFor(() => expect(api.emailOutbox).toHaveBeenCalledWith("test-token", "failed"));
  });

  it("refuses the page to anyone who is not a platform admin", async () => {
    platformAdmin = false;
    renderPage();
    expect(await screen.findByText(/platform admin/i)).toBeInTheDocument();
    expect(api.emailStatus).not.toHaveBeenCalled();
  });
});

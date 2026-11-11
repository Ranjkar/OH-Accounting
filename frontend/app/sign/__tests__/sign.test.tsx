import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import axe from "axe-core";
import enMessages from "../../../messages/en.json";
import nlMessages from "../../../messages/nl.json";
import { api, ApiError, SigningPage } from "@/lib/api";
import SignContractPage from "../[token]/page";

vi.mock("next/navigation", () => ({ useParams: () => ({ token: "tok-123" }) }));
vi.mock("@/components/glass/LanguageSelector", () => ({ default: () => <div /> }));

const PAGE: SigningPage = {
  reference: "OHA-2026-ABC123",
  status: "VIEWED",
  language: "en",
  content: {
    title: "Accounting Services Agreement",
    provider: { name: "OnHolland Accounting" },
    client: { name: "Client BV", kvk_number: "12345678", vat_number: "NL000099998B57", address: "Keizersgracht 1", representative: "Jan de Vries" },
    term: { start_date: "2026-11-11", end_date: "2027-11-10", months: 12, text: "12 months, from 11 November 2026 to 10 November 2027 inclusive" },
    services: [{ code: "bookkeeping", label: "Bookkeeping" }],
    fees: { fee_text: "EUR 250.00 per month (excl. VAT)", payment_terms_text: "14 days", notice_period_text: "30 days" },
    clauses: [{ key: "parties", heading: "1. Parties", body: "This agreement is entered into between OnHolland Accounting and Client BV." }],
  },
  signer_name: "Jan de Vries",
  signer_email_hint: "ja***@client.nl",
  consent_text: "I, Jan de Vries, confirm that I have read this agreement in full.",
  expires_at: "2026-11-25T10:00:00Z",
  already_signed: false,
  signed_at: null,
  signed_pdf_sha256: null,
  assurance_notice: "You sign with a simple electronic signature. This is not a qualified electronic signature.",
};

function renderPage(locale: "en-GB" | "nl-NL" = "en-GB") {
  const messages = locale === "nl-NL" ? nlMessages : enMessages;
  return render(
    <NextIntlClientProvider locale={locale} messages={messages} timeZone="Europe/Amsterdam">
      <SignContractPage />
    </NextIntlClientProvider>
  );
}

describe("public signing portal", () => {
  beforeEach(() => {
    vi.spyOn(api, "getSigningPage").mockResolvedValue(PAGE);
    vi.spyOn(api, "signContract").mockResolvedValue({ ...PAGE, already_signed: true, status: "ACTIVE", signed_at: "2026-11-11T12:00:00Z", signed_pdf_sha256: "ab".repeat(32) });
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("renders the full agreement, key terms and the assurance notice, and passes axe", async () => {
    const { container } = renderPage();
    expect(await screen.findByRole("heading", { level: 1, name: "Accounting Services Agreement" })).toBeInTheDocument();
    expect(screen.getByText("EUR 250.00 per month (excl. VAT)")).toBeInTheDocument();
    expect(screen.getByText("1. Parties")).toBeInTheDocument();
    expect(screen.getByText(/not a qualified electronic signature/)).toBeInTheDocument();
    expect(screen.getByLabelText("Full legal name")).toHaveAttribute("aria-describedby", "sign-name-help");
    const results = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
    expect(results.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(",")}`)).toEqual([]);
  });

  it("keeps the sign button disabled until consent is given, then signs and shows the confirmation with download", async () => {
    renderPage();
    const button = await screen.findByRole("button", { name: "Sign agreement" });
    expect(button).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Full legal name"), { target: { value: "Jan de Vries" } });
    fireEvent.change(screen.getByLabelText("Email address"), { target: { value: "jan@client.nl" } });
    fireEvent.click(screen.getByLabelText(/I have read the agreement in full/));
    expect(button).toBeEnabled();
    fireEvent.click(button);
    await waitFor(() => expect(api.signContract).toHaveBeenCalledWith("tok-123", { full_name: "Jan de Vries", email: "jan@client.nl", consent: true }));
    expect(await screen.findByRole("heading", { level: 1, name: "Agreement signed" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download signed PDF" })).toHaveAttribute("href", expect.stringContaining("/contracts/sign/tok-123/pdf"));
    expect(screen.getByText("ab".repeat(32))).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sign agreement" })).not.toBeInTheDocument();
  });

  it("shows the backend's rejection as an alert without leaving the form", async () => {
    vi.spyOn(api, "signContract").mockRejectedValue(new ApiError(403, "The email address does not match the address this agreement was sent to"));
    renderPage();
    await screen.findByRole("button", { name: "Sign agreement" });
    fireEvent.change(screen.getByLabelText("Full legal name"), { target: { value: "Jan de Vries" } });
    fireEvent.change(screen.getByLabelText("Email address"), { target: { value: "wrong@else.nl" } });
    fireEvent.click(screen.getByLabelText(/I have read the agreement in full/));
    fireEvent.click(screen.getByRole("button", { name: "Sign agreement" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("does not match");
    expect(screen.getByRole("button", { name: "Sign agreement" })).toBeInTheDocument();
  });

  it("explains an expired or unknown link instead of a blank page", async () => {
    vi.spyOn(api, "getSigningPage").mockRejectedValue(new ApiError(410, "This signing link has expired"));
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent("expired");
    cleanup();
    vi.spyOn(api, "getSigningPage").mockRejectedValue(new ApiError(404, "Unknown signing link"));
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent("unknown");
  });

  it("renders Dutch interface copy for the Dutch locale", async () => {
    renderPage("nl-NL");
    expect(await screen.findByRole("button", { name: "Overeenkomst ondertekenen" })).toBeInTheDocument();
    expect(screen.getByLabelText("Volledige wettelijke naam")).toBeInTheDocument();
  });
});

import { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import enMessages from "../../../messages/en.json";
import { api, ApiError, Contract, ContractDetail, User } from "@/lib/api";
import ContractsPage from "../page";
import ContractDetailPage from "../[id]/page";

const { routerPush } = vi.hoisted(() => ({ routerPush: vi.fn() }));
let role: User["role"] = "admin";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: routerPush, replace: vi.fn(), back: vi.fn() }),
  useSearchParams: () => ({ get: () => null }),
  useParams: () => ({ id: "7" }),
}));
vi.mock("@/components/AuthGuard", () => ({ default: ({ children }: { children: ReactNode }) => <>{children}</> }));
vi.mock("@/components/Shell", () => ({ default: ({ children }: { children: ReactNode }) => <>{children}</> }));
vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({ token: "test-token", user: { id: 1, email: "admin@acme.nl", full_name: "Admin", role, is_platform_admin: false, mfa_enabled: false } as User }),
}));
vi.mock("@/lib/company-context", () => ({ useCompany: () => ({ companies: [{ id: 1, name: "Client BV" }], selectedCompanyId: 1 }) }));

function contract(overrides: Partial<Contract> = {}): Contract {
  return {
    id: 7, tenant_id: 1, company_id: 1, company_name: "Client BV", reference: "OHA-2026-ABC123", status: "DRAFT", language: "nl", template_version_id: 1,
    start_date: "2026-11-11", end_date: "2027-11-10", term_months: 12, services: [{ code: "bookkeeping", label: "Boekhouding" }], monthly_fee: null, fee_description: null,
    currency: "EUR", payment_terms_days: null, notice_period_days: null, custom_clauses: null, signer_name: null, signer_email: "owner@client.nl", signer_title: null,
    renews_contract_id: null, renewal_contract_id: null, renewal_disabled: false, renewal_disabled_reason: null, created_source: "company_created",
    created_at: "2026-11-11T10:00:00Z", updated_at: "2026-11-11T10:00:00Z", approved_at: null, sent_at: null, viewed_at: null, signed_at: null, activated_at: null,
    expired_at: null, cancelled_at: null, terminated_at: null, termination_effective_date: null, closure_reason: null, signing_status: "not_sent", days_until_expiry: null,
    ...overrides,
  };
}

function detail(overrides: Partial<ContractDetail> = {}): ContractDetail {
  return {
    ...contract(), versions: [], invitations: [], signature: null, approval_missing: ["signer_name", "monthly_fee"], renews_reference: null, renewal_reference: null,
    events: [{ id: 1, event_type: "created", actor_type: "user", actor_user_id: 1, actor_name: "Admin", data: null, created_at: "2026-11-11T10:00:00Z" }],
    ...overrides,
  };
}

const wrap = (node: ReactNode) => render(<NextIntlClientProvider locale="en-GB" messages={enMessages} timeZone="Europe/Amsterdam">{node}</NextIntlClientProvider>);

describe("contracts administration", () => {
  beforeEach(() => {
    role = "admin";
    vi.spyOn(api, "listContracts").mockResolvedValue([contract(), contract({ id: 8, reference: "OHA-2026-DEF456", status: "SENT", signing_status: "awaiting", monthly_fee: "250.00" })]);
    vi.spyOn(api, "getContract").mockResolvedValue(detail());
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("lists contracts with status and signing pills and counts awaiting signatures", async () => {
    wrap(<ContractsPage />);
    expect(await screen.findAllByText("OHA-2026-ABC123")).not.toHaveLength(0);
    expect(screen.getAllByText("Awaiting signature").length).toBeGreaterThan(0);
    expect(screen.getAllByText("€250.00 / month").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "New contract" })).toBeInTheDocument();
  });

  it("shows a clear empty state when the feature flag is off", async () => {
    vi.spyOn(api, "listContracts").mockRejectedValue(new ApiError(404, "Contracts feature is not enabled (CONTRACTS_ENABLED)"));
    wrap(<ContractsPage />);
    expect(await screen.findByText("The Contracts module is not enabled on this server.")).toBeInTheDocument();
  });

  it("hides the create button from viewers", async () => {
    role = "viewer";
    wrap(<ContractsPage />);
    await screen.findAllByText("OHA-2026-ABC123");
    expect(screen.queryByRole("button", { name: "New contract" })).not.toBeInTheDocument();
  });

  it("blocks approval until required terms are set and explains what is missing", async () => {
    wrap(<ContractDetailPage />);
    expect(await screen.findByText(/Before this contract can be approved, set: signer name, fee/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Edit terms" })).toBeInTheDocument();
  });

  it("sends for signature and surfaces the signing link when no email provider is configured", async () => {
    vi.spyOn(api, "getContract").mockResolvedValue(detail({ status: "READY_TO_SEND", approval_missing: [], signer_name: "Jan de Vries", monthly_fee: "250.00" }));
    const send = vi.spyOn(api, "sendContract").mockResolvedValue({
      contract: contract({ status: "SENT", signing_status: "awaiting" }), email_sent: false, signing_link: "http://localhost:3000/sign/raw-token-xyz",
      invitation: { id: 1, signer_name: "Jan de Vries", signer_email: "owner@client.nl", status: "PENDING", is_renewal: false, created_at: "2026-11-11T10:00:00Z", expires_at: "2026-11-25T10:00:00Z", first_viewed_at: null, used_at: null, email_outbox_id: 1, email_status: "failed" },
    });
    wrap(<ContractDetailPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Send for signature" }));
    await waitFor(() => expect(send).toHaveBeenCalledWith("test-token", 7, false));
    expect(await screen.findByTestId("signing-link")).toHaveTextContent("http://localhost:3000/sign/raw-token-xyz");
  });

  it("asks for confirmation before terminating a signed contract", async () => {
    vi.spyOn(api, "getContract").mockResolvedValue(detail({ status: "ACTIVE", signing_status: "signed", approval_missing: [] }));
    const act = vi.spyOn(api, "contractAction").mockResolvedValue(detail({ status: "TERMINATED" }));
    wrap(<ContractDetailPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Terminate" }));
    const dialog = await screen.findByRole("dialog");
    expect(act).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Reason (optional)"), { target: { value: "non-payment" } });
    fireEvent.click(dialog.querySelector("button.btn-danger-v2") as HTMLElement);
    await waitFor(() => expect(act).toHaveBeenCalledWith("test-token", 7, "terminate", expect.objectContaining({ reason: "non-payment" })));
  });
});

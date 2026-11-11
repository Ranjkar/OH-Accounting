import { ReactNode, StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import enMessages from "../../../../messages/en.json";
import { api, LegalFormDefinition, SetupDraft } from "@/lib/api";
import NewCompanyPage from "../page";

const { routerPush, routerReplace, searchState } = vi.hoisted(() => ({
  routerPush: vi.fn(),
  routerReplace: vi.fn(),
  searchState: { draft: null as string | null },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: routerPush, replace: routerReplace }),
  useSearchParams: () => ({ get: (key: string) => (key === "draft" ? searchState.draft : null) }),
}));

vi.mock("@/components/AuthGuard", () => ({ default: ({ children }: { children: ReactNode }) => <>{children}</> }));
vi.mock("@/components/Shell", () => ({ default: ({ children }: { children: ReactNode }) => <>{children}</> }));
vi.mock("@/lib/auth-context", () => ({ useAuth: () => ({ token: "test-token", user: null, login: vi.fn(), logout: vi.fn() }) }));

/** BV must register at the KVK and has legal personality; a VvE must not.
 * That difference is what makes the KVK number conditionally required. */
const LEGAL_FORMS: LegalFormDefinition[] = [
  {
    id: 1, code: "BV", name_nl: "Besloten vennootschap", name_en: "Private limited company",
    has_legal_personality: true, liability: "limited", min_partners: 1, max_partners: null,
    requires_kvk_registration: true, subject_to_income_tax: false, subject_to_corporate_income_tax: true,
    subject_to_vat_by_default: true, payroll_tax_applies_if_employees: true, notes: null,
  },
  {
    id: 2, code: "VVE", name_nl: "Vereniging van eigenaars", name_en: "Homeowners association",
    has_legal_personality: false, liability: "joint", min_partners: 2, max_partners: null,
    requires_kvk_registration: false, subject_to_income_tax: false, subject_to_corporate_income_tax: false,
    subject_to_vat_by_default: false, payroll_tax_applies_if_employees: true, notes: null,
  },
];

const VALID_BTW = "NL000099998B57";
const VALID_IBAN = "NL91ABNA0417164300";

function makeDraft(overrides: Partial<SetupDraft> = {}): SetupDraft {
  return {
    id: 7,
    data: {},
    current_step: 0,
    created_company_id: null,
    created_at: "2026-11-01T10:00:00Z",
    updated_at: "2026-11-02T10:00:00Z",
    completed_at: null,
    ...overrides,
  };
}

function renderWizard() {
  return render(
    <NextIntlClientProvider locale="en-GB" messages={enMessages} timeZone="Europe/Amsterdam">
      <NewCompanyPage />
    </NextIntlClientProvider>
  );
}

const byId = (id: string) => document.getElementById(id) as HTMLInputElement | HTMLSelectElement;

describe("company setup wizard", () => {
  beforeEach(() => {
    searchState.draft = null;
    routerPush.mockReset();
    routerReplace.mockReset();
    vi.spyOn(api, "listLegalFormDefinitions").mockResolvedValue(LEGAL_FORMS);
    vi.spyOn(api, "listSetupDrafts").mockResolvedValue([]);
    vi.spyOn(api, "createSetupDraft").mockResolvedValue(makeDraft({ id: 5 }));
    vi.spyOn(api, "getSetupDraft").mockImplementation((_, id) => Promise.resolve(makeDraft({ id })));
    vi.spyOn(api, "updateSetupDraft").mockImplementation((_, id, data, step) => Promise.resolve(makeDraft({ id, data, current_step: step })));
    vi.spyOn(api, "validateSetupDraft").mockResolvedValue({ ok: true, issues: [], warnings: [] });
    vi.spyOn(api, "completeSetupDraft").mockResolvedValue({ company: { id: 11 } as never, financial_year_id: 1, bank_account_id: null, already_completed: false });
    vi.spyOn(api, "deleteSetupDraft").mockResolvedValue(undefined);
  });

  afterEach(() => {
    // Unmounting runs the page's own teardown, which clears the pending
    // debounce and flushes it as a single request -- so no timer outlives a test.
    cleanup();
    vi.restoreAllMocks();
  });

  describe("save and resume", () => {
    it("creates a draft when there is nothing to resume, and puts its id in the URL", async () => {
      renderWizard();
      await screen.findByRole("heading", { name: "Details" });
      expect(api.createSetupDraft).toHaveBeenCalledWith("test-token");
      expect(api.listSetupDrafts).toHaveBeenCalledWith("test-token");
      expect(routerReplace).toHaveBeenCalledWith("/companies/new?draft=5");
    });

    it("resumes the most recent open draft instead of silently starting a second one", async () => {
      vi.mocked(api.listSetupDrafts).mockResolvedValue([makeDraft({ id: 42, current_step: 1, data: { name: "Bakkerij Jansen", vat_registered: true } })]);
      renderWizard();
      await screen.findByRole("heading", { name: "Tax & VAT" });
      expect(api.createSetupDraft).not.toHaveBeenCalled();
      expect(screen.getByText("You are continuing the setup you saved earlier.")).toBeInTheDocument();
      expect(routerReplace).toHaveBeenCalledWith("/companies/new?draft=42");
    });

    it("opens the draft named in ?draft= even when a newer one exists", async () => {
      searchState.draft = "42";
      vi.mocked(api.listSetupDrafts).mockResolvedValue([makeDraft({ id: 99 })]);
      renderWizard();
      await screen.findByRole("heading", { name: "Details" });
      expect(api.getSetupDraft).toHaveBeenCalledWith("test-token", 42);
      expect(api.createSetupDraft).not.toHaveBeenCalled();
    });

    it("records the tax defaults the selects display, so completion cannot fail on them", async () => {
      vi.mocked(api.listSetupDrafts).mockResolvedValue([makeDraft({ id: 3, current_step: 1, data: { name: "Bakkerij Jansen", legal_form_code: "vve" } })]);
      renderWizard();
      await screen.findByRole("heading", { name: "Tax & VAT" });

      fireEvent.click(screen.getByRole("radio", { name: "Yes" }));
      // The seeded defaults must be visible in the selects, not just implied.
      expect(byId("setup-vat-frequency").value).toBe("quarterly");
      expect(byId("setup-vat-basis").value).toBe("invoice_based");

      fireEvent.change(screen.getByLabelText("VAT number"), { target: { value: VALID_BTW.toLowerCase() } });
      fireEvent.change(screen.getByLabelText("First financial year"), { target: { value: "2026" } });
      fireEvent.click(screen.getByRole("button", { name: "Next" }));

      await waitFor(() =>
        expect(api.updateSetupDraft).toHaveBeenCalledWith(
          "test-token",
          3,
          expect.objectContaining({
            vat_registered: true,
            vat_frequency: "quarterly",
            vat_accounting_basis: "invoice_based",
            vat_number: VALID_BTW,
            financial_year: 2026,
          }),
          2
        )
      );
      await screen.findByRole("heading", { name: "Bank account" });
    });

    it("creates exactly one draft when the effect runs twice (React StrictMode)", async () => {
      render(
        <StrictMode>
          <NextIntlClientProvider locale="en-GB" messages={enMessages} timeZone="Europe/Amsterdam">
            <NewCompanyPage />
          </NextIntlClientProvider>
        </StrictMode>
      );
      await screen.findByRole("heading", { name: "Details" });
      // StrictMode double-invokes effects in development; without sharing the
      // in-flight request this leaves an orphaned draft behind on every visit.
      expect(api.createSetupDraft).toHaveBeenCalledTimes(1);
      expect(api.listSetupDrafts).toHaveBeenCalledTimes(1);
    });

    it("discards the draft and returns to the company list", async () => {
      vi.mocked(api.listSetupDrafts).mockResolvedValue([makeDraft({ id: 42 })]);
      renderWizard();
      await screen.findByRole("heading", { name: "Details" });
      fireEvent.click(screen.getByRole("button", { name: "Discard draft" }));
      await waitFor(() => expect(api.deleteSetupDraft).toHaveBeenCalledWith("test-token", 42));
      expect(routerPush).toHaveBeenCalledWith("/companies");
    });
  });

  describe("conditionally required fields", () => {
    it("requires a KVK number for a legal form that must register, and blocks the step", async () => {
      vi.mocked(api.listSetupDrafts).mockResolvedValue([makeDraft({ id: 7, data: { name: "Bakkerij Jansen" } })]);
      renderWizard();
      await screen.findByRole("heading", { name: "Details" });

      fireEvent.change(screen.getByLabelText("Legal form"), { target: { value: "bv" } });
      expect(byId("setup-kvk").getAttribute("aria-required")).toBe("true");

      fireEvent.click(screen.getByRole("button", { name: "Next" }));
      expect(await screen.findByText("This legal form must be registered at the KVK -- enter the KVK number.")).toBeInTheDocument();
      expect(screen.getByRole("heading", { name: "Details" })).toBeInTheDocument();
      expect(byId("setup-kvk").getAttribute("aria-invalid")).toBe("true");
    });

    it("does not require a KVK number for a legal form that does not register", async () => {
      vi.mocked(api.listSetupDrafts).mockResolvedValue([makeDraft({ id: 7, data: { name: "VvE Het Hof" } })]);
      renderWizard();
      await screen.findByRole("heading", { name: "Details" });

      fireEvent.change(screen.getByLabelText("Legal form"), { target: { value: "vve" } });
      expect(byId("setup-kvk").getAttribute("aria-required")).toBeNull();

      fireEvent.click(screen.getByRole("button", { name: "Next" }));
      await screen.findByRole("heading", { name: "Tax & VAT" });
    });

    it("rejects an RSIN that fails the 11-check while leaving it optional", async () => {
      vi.mocked(api.listSetupDrafts).mockResolvedValue([makeDraft({ id: 7, data: { name: "Bakkerij Jansen", legal_form_code: "bv", kvk_number: "68750110" } })]);
      renderWizard();
      await screen.findByRole("heading", { name: "Details" });

      fireEvent.change(byId("setup-rsin"), { target: { value: "123456783" } });
      fireEvent.click(screen.getByRole("button", { name: "Next" }));
      expect(await screen.findByText("An RSIN is 9 digits and must pass the 11-check.")).toBeInTheDocument();
      expect(screen.getByRole("heading", { name: "Details" })).toBeInTheDocument();

      fireEvent.change(byId("setup-rsin"), { target: { value: "123456782" } });
      fireEvent.click(screen.getByRole("button", { name: "Next" }));
      await screen.findByRole("heading", { name: "Tax & VAT" });
    });

    it("makes the account holder name required only once an IBAN is entered", async () => {
      vi.mocked(api.listSetupDrafts).mockResolvedValue([makeDraft({ id: 7, current_step: 2, data: { name: "Bakkerij Jansen", legal_form_code: "vve", vat_registered: false, financial_year: 2026 } })]);
      renderWizard();
      await screen.findByRole("heading", { name: "Bank account" });

      fireEvent.change(byId("setup-iban"), { target: { value: VALID_IBAN } });
      expect(byId("setup-bank-name").getAttribute("aria-required")).toBe("true");
      fireEvent.click(screen.getByRole("button", { name: "Next" }));
      expect(await screen.findByText("Give the bank account a name.")).toBeInTheDocument();
      expect(screen.getByRole("heading", { name: "Bank account" })).toBeInTheDocument();

      fireEvent.change(screen.getByLabelText("Account holder name"), { target: { value: "Bakkerij Jansen" } });
      fireEvent.click(screen.getByRole("button", { name: "Next" }));
      await screen.findByRole("heading", { name: "Review" });
    });

    it("rejects an IBAN that fails its checksum", async () => {
      vi.mocked(api.listSetupDrafts).mockResolvedValue([makeDraft({ id: 7, current_step: 2, data: { name: "Bakkerij Jansen", legal_form_code: "vve", vat_registered: false, financial_year: 2026 } })]);
      renderWizard();
      await screen.findByRole("heading", { name: "Bank account" });

      fireEvent.change(byId("setup-iban"), { target: { value: "NL91ABNA0417164301" } });
      fireEvent.change(screen.getByLabelText("Account holder name"), { target: { value: "Bakkerij Jansen" } });
      fireEvent.click(screen.getByRole("button", { name: "Next" }));
      expect(await screen.findByText("This IBAN failed its checksum.")).toBeInTheDocument();
      expect(screen.getByRole("heading", { name: "Bank account" })).toBeInTheDocument();
    });

    it("lets banking be skipped, and remembers that the IBAN is then not required", async () => {
      vi.mocked(api.listSetupDrafts).mockResolvedValue([makeDraft({ id: 7, current_step: 2, data: { name: "Bakkerij Jansen", legal_form_code: "vve", vat_registered: false, financial_year: 2026 } })]);
      renderWizard();
      await screen.findByRole("heading", { name: "Bank account" });

      fireEvent.change(byId("setup-iban"), { target: { value: "NL91ABNA0417164301" } });
      fireEvent.click(screen.getByRole("button", { name: "Skip for now" }));
      await screen.findByRole("heading", { name: "Review" });
      expect(screen.getByText("Skipped -- add later")).toBeInTheDocument();
    });

    it("requires an explicit VAT answer before leaving the tax step", async () => {
      vi.mocked(api.listSetupDrafts).mockResolvedValue([makeDraft({ id: 7, current_step: 1, data: { name: "Bakkerij Jansen", legal_form_code: "vve", financial_year: 2026 } })]);
      renderWizard();
      await screen.findByRole("heading", { name: "Tax & VAT" });

      fireEvent.click(screen.getByRole("button", { name: "Next" }));
      expect(await screen.findByText("Indicate whether the company is registered for VAT.")).toBeInTheDocument();
      expect(screen.getByRole("heading", { name: "Tax & VAT" })).toBeInTheDocument();
    });

    it("shows the server's duplicate verdict on the review step", async () => {
      vi.mocked(api.listSetupDrafts).mockResolvedValue([
        makeDraft({ id: 7, current_step: 2, data: { name: "Bakkerij Jansen", legal_form_code: "vve", vat_registered: false, financial_year: 2026, bank_skipped: true } }),
      ]);
      vi.mocked(api.validateSetupDraft).mockResolvedValue({
        ok: false,
        issues: [{ field: "name", code: "duplicate", message: "A company with this name already exists in your organisation" }],
        warnings: [{ field: "rsin", code: "required", message: "add it when known" }],
      });
      renderWizard();
      await screen.findByRole("heading", { name: "Bank account" });

      fireEvent.click(screen.getByRole("button", { name: "Next" }));
      await screen.findByRole("heading", { name: "Review" });
      expect(screen.getByText("Fix these before creating the company")).toBeInTheDocument();
      expect(screen.getByText("A company with this name already exists in your organisation.")).toBeInTheDocument();
      expect(screen.getByText("RSIN: Recommended")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Create company" })).toBeDisabled();
    });
  });
});

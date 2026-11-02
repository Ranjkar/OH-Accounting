const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(
  path: string,
  options: RequestInit & { token?: string | null } = {}
): Promise<T> {
  const { token, headers, ...rest } = options;
  const res = await fetch(`${API_BASE}${path}`, {
    ...rest,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail ?? "Request failed");
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export type UserRole = "admin" | "accountant" | "viewer";
export type VatFrequency = "monthly" | "quarterly" | "annual";
export type VatPeriodStatus = "open" | "filed" | "paid";
export type VatAccountingBasis = "invoice_based" | "cash_based";

export type TransactionType = "SALES_INVOICE" | "PURCHASE_INVOICE" | "CREDIT_NOTE" | "RECEIPT" | "MANUAL_ENTRY";
export type LedgerSide = "SALES" | "PURCHASES";
export type VatTreatment =
  | "DOMESTIC_STANDARD"
  | "DOMESTIC_LOW"
  | "DOMESTIC_OTHER"
  | "PRIVATE_USE"
  | "DOMESTIC_ZERO_OR_EXEMPT"
  | "EXEMPT"
  | "DOMESTIC_REVERSE_CHARGE_RECEIVED"
  | "EXPORT_NON_EU"
  | "EU_SUPPLY"
  | "EU_DISTANCE_SALE"
  | "IMPORT_NON_EU"
  | "EU_ACQUISITION";
export type InputVatEligibility = "ELIGIBLE" | "INELIGIBLE" | "PARTIALLY_ELIGIBLE" | "REQUIRES_REVIEW";
export type TransactionApprovalStatus = "DRAFT" | "APPROVED" | "LOCKED";
export type TransactionPaymentStatus = "UNPAID" | "PARTIALLY_PAID" | "PAID" | "OVERDUE" | "UNKNOWN";
export type VatReturnStatus = "draft" | "needs_review" | "ready_for_approval" | "approved" | "locked";

export const SALES_TREATMENTS: VatTreatment[] = [
  "DOMESTIC_STANDARD",
  "DOMESTIC_LOW",
  "DOMESTIC_OTHER",
  "PRIVATE_USE",
  "DOMESTIC_ZERO_OR_EXEMPT",
  "EXEMPT",
  "EXPORT_NON_EU",
  "EU_SUPPLY",
  "EU_DISTANCE_SALE",
];
export const PURCHASE_TREATMENTS: VatTreatment[] = [
  "DOMESTIC_STANDARD",
  "DOMESTIC_LOW",
  "DOMESTIC_OTHER",
  "DOMESTIC_ZERO_OR_EXEMPT",
  "EXEMPT",
  "DOMESTIC_REVERSE_CHARGE_RECEIVED",
  "IMPORT_NON_EU",
  "EU_ACQUISITION",
];

export interface TransactionLineItem {
  line_number: number;
  description: string | null;
  net_amount: string;
  vat_rate: string;
  vat_amount: string;
  gross_amount: string;
  vat_treatment: VatTreatment;
  input_vat_eligibility: InputVatEligibility | null;
  deductible_vat_amount: string | null;
}

export interface Payment {
  id: number;
  amount: string;
  payment_date: string;
  reference: string | null;
  created_at: string;
}

export interface Transaction {
  id: number;
  company_id: number;
  financial_year_id: number;
  vat_period_id: number | null;
  source_document_id: number | null;
  corrects_transaction_id: number | null;
  transaction_type: TransactionType;
  ledger_side: LedgerSide;
  invoice_number: string | null;
  counterparty_name: string | null;
  counterparty_vat_number: string | null;
  counterparty_country_code: string | null;
  invoice_date: string;
  delivery_date: string | null;
  due_date: string | null;
  received_date: string | null;
  currency: string;
  fx_rate_to_eur: string | null;
  net_amount: string;
  vat_amount: string;
  gross_amount: string;
  net_amount_eur: string | null;
  vat_amount_eur: string | null;
  gross_amount_eur: string | null;
  payment_status: TransactionPaymentStatus;
  approval_status: TransactionApprovalStatus;
  accounting_classification: string | null;
  created_at: string;
}

export interface TransactionDetail extends Transaction {
  line_items: TransactionLineItem[];
  payments: Payment[];
  amount_paid: string;
  remaining_balance: string;
}

export interface VatReturn {
  id: number;
  company_id: number;
  vat_period_id: number;
  status: VatReturnStatus;
  rules_version: string;
  box_1a_net: string;
  box_1a_vat: string;
  box_1b_net: string;
  box_1b_vat: string;
  box_1c_net: string;
  box_1c_vat: string;
  box_1d_vat: string;
  box_1e_net: string;
  box_2a_net: string;
  box_2a_vat: string;
  box_3a_net: string;
  box_3b_net: string;
  box_3c_net: string;
  box_4a_net: string;
  box_4a_vat: string;
  box_4b_net: string;
  box_4b_vat: string;
  box_5a_vat: string;
  box_5b_vat: string;
  net_payable: string;
  computed_at: string | null;
  approved_by_user_id: number | null;
  approved_at: string | null;
  locked_at: string | null;
}

export interface Reconciliation {
  vat_return: VatReturn;
  sales_total_net: string;
  purchases_total_net: string;
  sales_vat_by_rate: Record<string, string>;
  purchase_vat_by_rate: Record<string, string>;
  pending_documents: { id: number; original_filename: string; status: string }[];
  duplicate_documents: { id: number; original_filename: string; duplicate_of_document_id: number | null }[];
  validation_errors: { document_id: number; rule_code: string; message: string }[];
  unresolved_fx_transaction_ids: number[];
  corrections: Transaction[];
}

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: UserRole;
}

export interface Company {
  id: number;
  name: string;
  kvk_number: string | null;
  vat_number: string | null;
  address: string | null;
  vat_frequency: VatFrequency;
  vat_accounting_basis: VatAccountingBasis;
  input_vat_pro_rata_percentage: string | null;
}

export interface VatPeriod {
  id: number;
  label: string;
  start_date: string;
  end_date: string;
  filing_deadline: string;
  payment_deadline: string;
  status: VatPeriodStatus;
}

export interface FinancialYear {
  id: number;
  year: number;
  start_date: string;
  end_date: string;
  vat_periods: VatPeriod[];
}

export type DocumentStatus =
  | "pending"
  | "processing"
  | "extracted"
  | "needs_review"
  | "approved"
  | "rejected"
  | "failed";
export type DocumentType =
  | "SALES_INVOICE"
  | "PURCHASE_INVOICE"
  | "CREDIT_NOTE"
  | "RECEIPT"
  | "BANK_STATEMENT"
  | "OTHER";
export type PaymentStatus = "UNPAID" | "PARTIALLY_PAID" | "PAID" | "UNKNOWN";
export type ValidationSeverity = "info" | "warning" | "error";

export interface DocumentSummary {
  id: number;
  company_id: number;
  financial_year_id: number | null;
  original_filename: string;
  content_type: string;
  file_size: number;
  status: DocumentStatus;
  document_type: DocumentType | null;
  classification_confidence: number | null;
  is_duplicate: boolean;
  duplicate_of_document_id: number | null;
  error_message: string | null;
  created_at: string;
  processed_at: string | null;
}

export interface ExtractedFields {
  invoice_number: string | null;
  invoice_date: string | null;
  due_date: string | null;
  supplier_name: string | null;
  supplier_address: string | null;
  supplier_vat_number: string | null;
  customer_name: string | null;
  customer_vat_number: string | null;
  description: string | null;
  net_amount: number | null;
  vat_rate: number | null;
  vat_amount: number | null;
  gross_amount: number | null;
  currency: string | null;
  payment_terms: string | null;
  iban: string | null;
  credit_note_reference: string | null;
  payment_status: PaymentStatus;
  field_sources: Record<string, string> | null;
  review_status: string;
  reviewed_by_user_id: number | null;
  reviewed_at: string | null;
}

export interface LineItem {
  line_number: number;
  description: string | null;
  quantity: number | null;
  unit_price: number | null;
  net_amount: number | null;
  vat_rate: number | null;
  vat_amount: number | null;
  gross_amount: number | null;
  source_ref: string | null;
}

export interface ValidationResult {
  rule_code: string;
  severity: ValidationSeverity;
  message: string;
}

export interface DocumentDetail extends DocumentSummary {
  fields: ExtractedFields | null;
  line_items: LineItem[];
  validation_results: ValidationResult[];
}

export interface DashboardSummary {
  company_count: number;
  open_vat_periods: number;
  upcoming_deadlines: {
    company_id: number;
    company_name: string;
    period_label: string;
    filing_deadline: string;
    payment_deadline: string;
  }[];
}

export const api = {
  login: (email: string, password: string) =>
    request<{ access_token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  me: (token: string) => request<User>("/auth/me", { token }),
  listCompanies: (token: string) => request<Company[]>("/companies", { token }),
  createCompany: (
    token: string,
    payload: Pick<Company, "name" | "kvk_number" | "vat_number" | "address" | "vat_frequency">
  ) =>
    request<Company>("/companies", {
      method: "POST",
      token,
      body: JSON.stringify(payload),
    }),
  getCompany: (token: string, id: number) => request<Company>(`/companies/${id}`, { token }),
  listFinancialYears: (token: string, companyId: number) =>
    request<FinancialYear[]>(`/companies/${companyId}/financial-years`, { token }),
  createFinancialYear: (token: string, companyId: number, year: number) =>
    request<FinancialYear>(`/companies/${companyId}/financial-years`, {
      method: "POST",
      token,
      body: JSON.stringify({ year }),
    }),
  dashboard: (token: string) => request<DashboardSummary>("/dashboard", { token }),

  uploadDocument: async (
    token: string,
    file: File,
    companyId: number,
    financialYearId?: number
  ): Promise<DocumentSummary> => {
    const params = new URLSearchParams({ company_id: String(companyId) });
    if (financialYearId) params.set("financial_year_id", String(financialYearId));
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${API_BASE}/documents/upload?${params}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: form,
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      throw new ApiError(res.status, body.detail ?? "Upload failed");
    }
    return res.json();
  },
  listDocuments: (token: string, filters: { company_id?: number; status_filter?: DocumentStatus } = {}) => {
    const params = new URLSearchParams();
    if (filters.company_id) params.set("company_id", String(filters.company_id));
    if (filters.status_filter) params.set("status_filter", filters.status_filter);
    const qs = params.toString();
    return request<DocumentSummary[]>(`/documents${qs ? `?${qs}` : ""}`, { token });
  },
  getDocument: (token: string, id: number) => request<DocumentDetail>(`/documents/${id}`, { token }),
  documentFileBlobUrl: async (token: string, id: number): Promise<string> => {
    const res = await fetch(`${API_BASE}/documents/${id}/file`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new ApiError(res.status, "Failed to load file");
    const blob = await res.blob();
    return URL.createObjectURL(blob);
  },
  reprocessDocument: (token: string, id: number) =>
    request<DocumentSummary>(`/documents/${id}/reprocess`, { method: "POST", token }),
  updateDocumentFields: (token: string, id: number, payload: Partial<ExtractedFields>) =>
    request<DocumentDetail>(`/documents/${id}/fields`, {
      method: "PATCH",
      token,
      body: JSON.stringify(payload),
    }),
  approveDocument: (token: string, id: number) =>
    request<DocumentSummary>(`/documents/${id}/approve`, { method: "POST", token }),
  rejectDocument: (token: string, id: number, reason: string) =>
    request<DocumentSummary>(`/documents/${id}/reject`, {
      method: "POST",
      token,
      body: JSON.stringify({ reason }),
    }),
  reassignDocument: (
    token: string,
    id: number,
    payload: { company_id?: number; financial_year_id?: number }
  ) =>
    request<DocumentSummary>(`/documents/${id}/assignment`, {
      method: "PATCH",
      token,
      body: JSON.stringify(payload),
    }),

  updateCompany: (
    token: string,
    id: number,
    payload: { vat_accounting_basis?: VatAccountingBasis; input_vat_pro_rata_percentage?: number | null }
  ) =>
    request<Company>(`/companies/${id}`, { method: "PATCH", token, body: JSON.stringify(payload) }),

  listTransactions: (
    token: string,
    filters: { company_id?: number; vat_period_id?: number; transaction_type?: TransactionType } = {}
  ) => {
    const params = new URLSearchParams();
    if (filters.company_id) params.set("company_id", String(filters.company_id));
    if (filters.vat_period_id) params.set("vat_period_id", String(filters.vat_period_id));
    if (filters.transaction_type) params.set("transaction_type", filters.transaction_type);
    const qs = params.toString();
    return request<Transaction[]>(`/transactions${qs ? `?${qs}` : ""}`, { token });
  },
  getTransaction: (token: string, id: number) => request<TransactionDetail>(`/transactions/${id}`, { token }),
  createManualEntry: (
    token: string,
    payload: {
      company_id: number;
      financial_year_id: number;
      ledger_side: LedgerSide;
      invoice_date: string;
      due_date?: string | null;
      currency?: string;
      fx_rate_to_eur?: string | null;
      counterparty_name?: string | null;
      counterparty_vat_number?: string | null;
      accounting_classification?: string | null;
      line_items: {
        description?: string | null;
        net_amount: string;
        vat_rate: string;
        vat_amount: string;
        vat_treatment: VatTreatment;
        input_vat_eligibility?: InputVatEligibility | null;
      }[];
    }
  ) => request<TransactionDetail>("/transactions", { method: "POST", token, body: JSON.stringify(payload) }),
  recordPayment: (token: string, transactionId: number, payload: { amount: string; payment_date: string; reference?: string }) =>
    request<TransactionDetail>(`/transactions/${transactionId}/payments`, {
      method: "POST",
      token,
      body: JSON.stringify(payload),
    }),
  approveTransaction: (token: string, id: number) =>
    request<TransactionDetail>(`/transactions/${id}/approve`, { method: "POST", token }),
  createCorrection: (
    token: string,
    transactionId: number,
    payload: {
      financial_year_id: number;
      line_items: {
        description?: string | null;
        net_amount: string;
        vat_rate: string;
        vat_amount: string;
        vat_treatment: VatTreatment;
        input_vat_eligibility?: InputVatEligibility | null;
      }[];
    }
  ) =>
    request<TransactionDetail>(`/transactions/${transactionId}/corrections`, {
      method: "POST",
      token,
      body: JSON.stringify(payload),
    }),

  getOrComputeVatReturn: (token: string, companyId: number, vatPeriodId: number) =>
    request<VatReturn>(`/vat-returns?company_id=${companyId}&vat_period_id=${vatPeriodId}`, { token }),
  getReconciliation: (token: string, vatReturnId: number) =>
    request<Reconciliation>(`/vat-returns/${vatReturnId}/reconciliation`, { token }),
  recalculateVatReturn: (token: string, vatReturnId: number) =>
    request<VatReturn>(`/vat-returns/${vatReturnId}/recalculate`, { method: "POST", token }),
  submitVatReturnForApproval: (token: string, vatReturnId: number) =>
    request<VatReturn>(`/vat-returns/${vatReturnId}/submit-for-approval`, { method: "POST", token }),
  approveVatReturn: (token: string, vatReturnId: number) =>
    request<VatReturn>(`/vat-returns/${vatReturnId}/approve`, { method: "POST", token }),
  lockVatReturn: (token: string, vatReturnId: number) =>
    request<VatReturn>(`/vat-returns/${vatReturnId}/lock`, { method: "POST", token }),
};

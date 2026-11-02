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
  expense_category: string | null;
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
  upload_batch_id: number | null;
  upload_category: LedgerSide | null;
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

export type BatchStatus = "processing" | "completed";

export interface BatchCounts {
  total: number;
  extracted: number;
  needs_review: number;
  duplicates: number;
  failed: number;
  approved: number;
  pending_or_processing: number;
  rejected: number;
}

export interface Batch {
  id: number;
  company_id: number;
  financial_year_id: number;
  category: LedgerSide;
  status: BatchStatus;
  created_at: string;
  counts: BatchCounts;
}

export interface BatchDetail extends Batch {
  documents: DocumentSummary[];
}

export interface RejectedFile {
  filename: string;
  reason: string;
}

export interface BatchUploadResponse {
  batch: Batch;
  documents: DocumentSummary[];
  rejected_files: RejectedFile[];
}

export interface BulkActionItemResult {
  document_id: number;
  success: boolean;
  detail: string;
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
    vat_period_id: number;
    period_label: string;
    filing_deadline: string;
    payment_deadline: string;
    is_overdue: boolean;
  }[];
  companies_requiring_attention: { company_id: number; company_name: string; reasons: string[] }[];
  vat_returns_awaiting_review: number;
  vat_returns_approved: number;
  overdue_vat_returns: number;
  documents_awaiting_approval: number;
  unmatched_payments: number;
  outstanding_customer_info: number;
  estimated_vat_payable: string;
  estimated_vat_refundable: string;
  generated_at: string;
}

export type NoteType = "INTERNAL" | "CUSTOMER_QUESTION" | "MISSING_DOCUMENT_REQUEST";
export type NoteStatus = "OPEN" | "ANSWERED" | "RESOLVED";

export interface Note {
  id: number;
  note_type: NoteType;
  status: NoteStatus;
  body: string;
  related_entity_type: string | null;
  related_entity_id: number | null;
  author_user_id: number;
  created_at: string;
  resolved_at: string | null;
}

export interface CompletenessRow {
  requirement: string;
  complete: boolean;
  detail: string;
}

export interface PeriodCompleteness {
  vat_period_id: number;
  label: string;
  start_date: string;
  end_date: string;
  filing_deadline: string;
  vat_return_status: VatReturnStatus | null;
  rows: CompletenessRow[];
}

export interface CompanyWorkspace {
  company_id: number;
  company_name: string;
  vat_frequency: string;
  vat_accounting_basis: string;
  financial_year_count: number;
  sales_invoice_count: number;
  purchase_invoice_count: number;
  transaction_count: number;
  payment_count: number;
  document_count: number;
  documents_awaiting_approval: number;
  open_notes: number;
  open_customer_questions: number;
  vat_returns: { id: number; vat_period_id: number; period_label: string; status: string; net_payable: string }[];
  period_completeness: PeriodCompleteness[];
  notes: Note[];
}

export type CalendarStatus = "completed" | "upcoming" | "overdue" | "pending";

export interface TaxCalendarEntry {
  company_id: number;
  company_name: string;
  vat_period_id: number;
  financial_year: number;
  period_label: string;
  vat_frequency: string;
  start_date: string;
  end_date: string;
  filing_deadline: string;
  payment_deadline: string;
  calendar_status: CalendarStatus;
  vat_return_id: number | null;
}

export interface AssistantResponse {
  facts: Record<string, unknown>;
  answer: string;
  model: string;
  generated_at: string;
  disclaimer: string;
}

// ---- Phase 6: banking, reconciliation, automation ----

export type BankSourceFormat = "CAMT053" | "CAMT054" | "MT940" | "CSV";
export type BankConsentStatus = "NOT_CONNECTED" | "FILE_IMPORT_ONLY" | "CONNECTED";
export type ReconciliationStatus =
  | "IMPORTED"
  | "UNMATCHED"
  | "SUGGESTED_MATCH"
  | "MATCHED"
  | "PARTIALLY_MATCHED"
  | "MANUALLY_RECONCILED"
  | "EXCLUDED";
export type MatchStatus = "SUGGESTED" | "APPROVED" | "REJECTED" | "REVERSED";
export type RecurringFrequency = "WEEKLY" | "MONTHLY" | "QUARTERLY" | "ANNUAL";
export type RecurringStatus = "ACTIVE" | "MISSING" | "STOPPED";
export type AnomalySeverity = "info" | "warning" | "critical";
export type AnomalyStatus = "OPEN" | "ACKNOWLEDGED" | "DISMISSED";
export type CategorizationRuleType = "SUPPLIER_NAME" | "IBAN" | "DESCRIPTION_PATTERN";

export interface BankAccount {
  id: number;
  company_id: number;
  iban: string;
  account_name: string;
  currency: string;
  consent_status: BankConsentStatus;
  created_at: string;
}

export interface BankImportBatch {
  id: number;
  bank_account_id: number;
  source_format: BankSourceFormat;
  original_filename: string;
  transaction_count: number;
  duplicate_count: number;
  error_count: number;
  error_message: string | null;
  imported_by_user_id: number;
  imported_at: string;
}

export interface PaymentMatch {
  id: number;
  bank_transaction_id: number;
  accounting_transaction_id: number;
  allocated_amount: string;
  confidence_score: string;
  confidence_level: string;
  match_signals: Record<string, unknown>;
  status: string;
  created_at: string;
  approved_by_user_id: number | null;
  approved_at: string | null;
  payment_id: number | null;
}

export interface BankTransaction {
  id: number;
  bank_account_id: number;
  import_batch_id: number;
  external_transaction_id: string | null;
  booking_date: string;
  value_date: string | null;
  amount: string;
  currency: string;
  counterparty_name: string | null;
  counterparty_iban: string | null;
  payment_reference: string | null;
  description: string | null;
  source_format: BankSourceFormat;
  reconciliation_status: ReconciliationStatus;
  created_at: string;
}

export interface BankTransactionDetail extends BankTransaction {
  matches: PaymentMatch[];
}

export interface CategorizationRule {
  id: number;
  company_id: number;
  rule_type: CategorizationRuleType;
  match_value: string;
  category: string;
  created_at: string;
}

export interface CategorySuggestion {
  suggested_category: string;
  confidence: number;
  reasoning: string;
  evidence: string[];
  requires_accountant_review: boolean;
}

export interface RecurringPattern {
  id: number;
  company_id: number;
  counterparty_name: string | null;
  counterparty_iban: string | null;
  frequency: RecurringFrequency;
  expected_amount: string;
  last_transaction_date: string;
  next_expected_date: string;
  status: RecurringStatus;
  occurrence_count: number;
}

export interface AnomalyFlag {
  id: number;
  company_id: number;
  rule_code: string;
  severity: AnomalySeverity;
  message: string;
  evidence: Record<string, unknown>;
  related_entity_type: string;
  related_entity_id: number;
  status: AnomalyStatus;
  created_at: string;
}

export interface AutomationCentreSummary {
  company_id: number;
  unmatched_transactions: number;
  suggested_matches: number;
  high_confidence_suggested_matches: number;
  missing_invoices_estimate: number;
  expenses_awaiting_categorization: number;
  open_anomalies: number;
  recurring_missing: number;
  failed_import_batches: number;
  pending_notes: number;
}

export interface CashFlowForecast {
  as_of: string;
  net_bank_transaction_movement: string;
  net_bank_transaction_movement_disclaimer: string;
  expected_incoming_total: string;
  expected_outgoing_total: string;
  outstanding_sales_invoice_count: number;
  outstanding_purchase_invoice_count: number;
  recurring_expenses_monthly_equivalent: string;
  recurring_pattern_count: number;
  forecast_vat_payable: string;
  forecast_vat_refundable: string;
  forecast_vat_disclaimer: string;
  monthly_projection: {
    month: string;
    expected_incoming: string;
    expected_outgoing: string;
    net: string;
    is_estimate: boolean;
  }[];
  monthly_projection_disclaimer: string;
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

  dashboard: (token: string, filters: { company_id?: number; financial_year_id?: number } = {}) => {
    const params = new URLSearchParams();
    if (filters.company_id) params.set("company_id", String(filters.company_id));
    if (filters.financial_year_id) params.set("financial_year_id", String(filters.financial_year_id));
    const qs = params.toString();
    return request<DashboardSummary>(`/dashboard${qs ? `?${qs}` : ""}`, { token });
  },

  getCompanyWorkspace: (token: string, companyId: number) =>
    request<CompanyWorkspace>(`/companies/${companyId}/workspace`, { token }),
  listNotes: (token: string, companyId: number) => request<Note[]>(`/companies/${companyId}/notes`, { token }),
  createNote: (
    token: string,
    companyId: number,
    payload: { note_type: NoteType; body: string; related_entity_type?: string; related_entity_id?: number }
  ) => request<Note>(`/companies/${companyId}/notes`, { method: "POST", token, body: JSON.stringify(payload) }),
  updateNoteStatus: (token: string, noteId: number, status: NoteStatus) =>
    request<Note>(`/notes/${noteId}/status`, { method: "PATCH", token, body: JSON.stringify({ status }) }),

  getTaxCalendar: (token: string, filters: { company_id?: number; year?: number } = {}) => {
    const params = new URLSearchParams();
    if (filters.company_id) params.set("company_id", String(filters.company_id));
    if (filters.year) params.set("year", String(filters.year));
    const qs = params.toString();
    return request<TaxCalendarEntry[]>(`/tax-calendar${qs ? `?${qs}` : ""}`, { token });
  },

  askAssistant: (token: string, payload: { company_id: number; question: string; vat_period_id?: number }) =>
    request<AssistantResponse>("/assistant/ask", { method: "POST", token, body: JSON.stringify(payload) }),
  assistantCompanySummary: (token: string, companyId: number) =>
    request<AssistantResponse>(`/assistant/company-summary?company_id=${companyId}`, { token }),
  assistantVatReturnExplanation: (token: string, vatReturnId: number) =>
    request<AssistantResponse>(`/assistant/vat-return-explanation/${vatReturnId}`, { token }),
  assistantMissingDocuments: (token: string, companyId: number) =>
    request<AssistantResponse>(`/assistant/missing-documents?company_id=${companyId}`, { token }),
  assistantPeriodComparison: (token: string, companyId: number, periodIdA: number, periodIdB: number) =>
    request<AssistantResponse>(
      `/assistant/period-comparison?company_id=${companyId}&vat_period_id_a=${periodIdA}&vat_period_id_b=${periodIdB}`,
      { token }
    ),

  vatReturnReportUrl: (vatReturnId: number, format: "pdf" | "xlsx" | "csv"): string =>
    `${API_BASE}/reports/vat-return/${vatReturnId}?format=${format}`,
  financialOverviewReportUrl: (companyId: number, financialYearId: number, format: "pdf" | "xlsx" | "csv"): string =>
    `${API_BASE}/reports/financial-overview?company_id=${companyId}&financial_year_id=${financialYearId}&format=${format}`,
  downloadReport: async (token: string, url: string, filename: string): Promise<void> => {
    const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
    if (!res.ok) throw new ApiError(res.status, "Failed to generate report");
    const blob = await res.blob();
    const objectUrl = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = objectUrl;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(objectUrl);
  },
  getPeriodComparison: (token: string, companyId: number, financialYearId: number) =>
    request<{
      financial_year: number;
      periods: { label: string; sales_net: string; purchases_net: string; income_minus_expense: string; transaction_count: number }[];
      total_sales_net: string;
      total_purchases_net: string;
      net_income: string;
      payment_status_counts: Record<string, number>;
    }>(`/reports/period-comparison?company_id=${companyId}&financial_year_id=${financialYearId}`, { token }),

  uploadBatch: async (
    token: string,
    files: File[],
    companyId: number,
    financialYearId: number,
    category: LedgerSide
  ): Promise<BatchUploadResponse> => {
    const params = new URLSearchParams({
      company_id: String(companyId),
      financial_year_id: String(financialYearId),
      category,
    });
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    const res = await fetch(`${API_BASE}/batches/upload?${params}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: form,
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      throw new ApiError(res.status, body.detail ?? "Batch upload failed");
    }
    return res.json();
  },
  listBatches: (token: string, filters: { company_id?: number; category?: LedgerSide } = {}) => {
    const params = new URLSearchParams();
    if (filters.company_id) params.set("company_id", String(filters.company_id));
    if (filters.category) params.set("category", filters.category);
    const qs = params.toString();
    return request<Batch[]>(`/batches${qs ? `?${qs}` : ""}`, { token });
  },
  getBatch: (token: string, batchId: number) => request<BatchDetail>(`/batches/${batchId}`, { token }),
  bulkApproveDocuments: (token: string, batchId: number, documentIds: number[]) =>
    request<{ results: BulkActionItemResult[] }>(`/batches/${batchId}/approve`, {
      method: "POST",
      token,
      body: JSON.stringify({ document_ids: documentIds }),
    }),
  bulkRejectDocuments: (token: string, batchId: number, documentIds: number[], reason: string) =>
    request<{ results: BulkActionItemResult[] }>(`/batches/${batchId}/reject`, {
      method: "POST",
      token,
      body: JSON.stringify({ document_ids: documentIds, reason }),
    }),
  deleteDocument: async (token: string, documentId: number): Promise<void> => {
    const res = await fetch(`${API_BASE}/documents/${documentId}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok && res.status !== 204) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      throw new ApiError(res.status, body.detail ?? "Failed to delete document");
    }
  },
  batchExportUrl: (batchId: number) => `${API_BASE}/batches/${batchId}/export`,

  // ---- Phase 6: banking ----
  listBankAccounts: (token: string, companyId?: number) =>
    request<BankAccount[]>(`/bank-accounts${companyId ? `?company_id=${companyId}` : ""}`, { token }),
  createBankAccount: (token: string, payload: { company_id: number; iban: string; account_name: string }) =>
    request<BankAccount>("/bank-accounts", { method: "POST", token, body: JSON.stringify(payload) }),
  importBankStatement: async (
    token: string,
    bankAccountId: number,
    sourceFormat: BankSourceFormat,
    file: File
  ): Promise<BankImportBatch> => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(
      `${API_BASE}/bank-accounts/${bankAccountId}/import?source_format=${sourceFormat}`,
      { method: "POST", headers: { Authorization: `Bearer ${token}` }, body: form }
    );
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      throw new ApiError(res.status, body.detail ?? "Import failed");
    }
    return res.json();
  },
  listImportBatches: (token: string, bankAccountId: number) =>
    request<BankImportBatch[]>(`/bank-accounts/${bankAccountId}/import-batches`, { token }),
  listBankTransactions: (
    token: string,
    filters: { company_id?: number; bank_account_id?: number; reconciliation_status?: ReconciliationStatus } = {}
  ) => {
    const params = new URLSearchParams();
    if (filters.company_id) params.set("company_id", String(filters.company_id));
    if (filters.bank_account_id) params.set("bank_account_id", String(filters.bank_account_id));
    if (filters.reconciliation_status) params.set("reconciliation_status", filters.reconciliation_status);
    const qs = params.toString();
    return request<BankTransaction[]>(`/bank-transactions${qs ? `?${qs}` : ""}`, { token });
  },
  getBankTransaction: (token: string, id: number) => request<BankTransactionDetail>(`/bank-transactions/${id}`, { token }),
  suggestMatches: (token: string, bankTransactionId: number) =>
    request<PaymentMatch[]>(`/bank-transactions/${bankTransactionId}/suggest-matches`, { method: "POST", token }),
  excludeBankTransaction: (token: string, bankTransactionId: number) =>
    request<BankTransaction>(`/bank-transactions/${bankTransactionId}/exclude`, { method: "POST", token }),
  approveMatch: (token: string, matchId: number) =>
    request<PaymentMatch>(`/payment-matches/${matchId}/approve`, { method: "POST", token }),
  rejectMatch: (token: string, matchId: number) =>
    request<PaymentMatch>(`/payment-matches/${matchId}/reject`, { method: "POST", token }),
  reverseMatch: (token: string, matchId: number, reason: string) =>
    request<PaymentMatch>(`/payment-matches/${matchId}/reverse`, { method: "POST", token, body: JSON.stringify({ reason }) }),
  bulkApproveHighConfidence: (token: string, companyId: number) =>
    request<PaymentMatch[]>(`/payment-matches/bulk-approve-high-confidence?company_id=${companyId}`, { method: "POST", token }),

  // ---- Phase 6: expense categorization ----
  listCategorizationRules: (token: string, companyId: number) =>
    request<CategorizationRule[]>(`/categorization-rules?company_id=${companyId}`, { token }),
  createCategorizationRule: (
    token: string,
    payload: { company_id: number; rule_type: CategorizationRuleType; match_value: string; category: string }
  ) => request<CategorizationRule>("/categorization-rules", { method: "POST", token, body: JSON.stringify(payload) }),
  suggestCategory: (token: string, transactionId: number) =>
    request<CategorySuggestion>(`/transactions/${transactionId}/category-suggestion`, { token }),
  categorizeTransaction: (token: string, transactionId: number, category: string, rememberAsRule: boolean) =>
    request<{ transaction_id: number; expense_category: string; rule_created_id: number | null }>(
      `/transactions/${transactionId}/categorize`,
      { method: "POST", token, body: JSON.stringify({ category, remember_as_rule: rememberAsRule }) }
    ),
  applyCategorizationRules: (token: string, companyId: number) =>
    request<{ transactions_checked: number; rules_applied: number }>(
      `/companies/${companyId}/apply-categorization-rules`,
      { method: "POST", token }
    ),
  listUncategorizedTransactions: (token: string, companyId: number) =>
    request<Transaction[]>(`/transactions?company_id=${companyId}`, { token }).then((txs) =>
      txs.filter((t) => t.ledger_side === "PURCHASES" && !t.expense_category)
    ),

  // ---- Phase 6: recurring + anomalies ----
  detectRecurring: (token: string, companyId: number) =>
    request<RecurringPattern[]>(`/companies/${companyId}/detect-recurring`, { method: "POST", token }),
  listRecurringPatterns: (token: string, companyId: number) =>
    request<RecurringPattern[]>(`/companies/${companyId}/recurring-patterns`, { token }),
  detectAnomalies: (token: string, companyId: number) =>
    request<AnomalyFlag[]>(`/companies/${companyId}/detect-anomalies`, { method: "POST", token }),
  listAnomalies: (token: string, companyId: number, statusFilter?: AnomalyStatus) =>
    request<AnomalyFlag[]>(
      `/companies/${companyId}/anomalies${statusFilter ? `?status_filter=${statusFilter}` : ""}`,
      { token }
    ),
  acknowledgeAnomaly: (token: string, anomalyId: number) =>
    request<AnomalyFlag>(`/anomalies/${anomalyId}/acknowledge`, { method: "POST", token }),
  dismissAnomaly: (token: string, anomalyId: number) =>
    request<AnomalyFlag>(`/anomalies/${anomalyId}/dismiss`, { method: "POST", token }),

  // ---- Phase 6: automation centre + cash flow ----
  automationCentreSummary: (token: string, companyId: number) =>
    request<AutomationCentreSummary>(`/companies/${companyId}/automation-centre`, { token }),
  cashFlowForecast: (token: string, companyId: number, monthsAhead = 3) =>
    request<CashFlowForecast>(`/companies/${companyId}/cash-flow-forecast?months_ahead=${monthsAhead}`, { token }),
};

import enum


class UserRole(str, enum.Enum):
    admin = "admin"
    accountant = "accountant"
    viewer = "viewer"
    customer = "customer"
    employee = "employee"


class VatFrequency(str, enum.Enum):
    monthly = "monthly"
    quarterly = "quarterly"
    annual = "annual"


class VatPeriodStatus(str, enum.Enum):
    open = "open"
    filed = "filed"
    paid = "paid"


class DocumentStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    extracted = "extracted"
    needs_review = "needs_review"
    approved = "approved"
    rejected = "rejected"
    failed = "failed"


class DocumentType(str, enum.Enum):
    sales_invoice = "SALES_INVOICE"
    purchase_invoice = "PURCHASE_INVOICE"
    credit_note = "CREDIT_NOTE"
    receipt = "RECEIPT"
    bank_statement = "BANK_STATEMENT"
    other = "OTHER"


class PaymentStatus(str, enum.Enum):
    unpaid = "UNPAID"
    partially_paid = "PARTIALLY_PAID"
    paid = "PAID"
    overdue = "OVERDUE"
    unknown = "UNKNOWN"


class ValidationSeverity(str, enum.Enum):
    info = "info"
    warning = "warning"
    error = "error"


class ProcessingAttemptStatus(str, enum.Enum):
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class VatAccountingBasis(str, enum.Enum):
    invoice_based = "invoice_based"
    cash_based = "cash_based"


class TransactionType(str, enum.Enum):
    sales_invoice = "SALES_INVOICE"
    purchase_invoice = "PURCHASE_INVOICE"
    credit_note = "CREDIT_NOTE"
    receipt = "RECEIPT"
    manual_entry = "MANUAL_ENTRY"


class LedgerSide(str, enum.Enum):
    sales = "SALES"
    purchases = "PURCHASES"


class VatTreatment(str, enum.Enum):
    domestic_standard = "DOMESTIC_STANDARD"  # 21% -> box 1a
    domestic_low = "DOMESTIC_LOW"  # 9% -> box 1b
    domestic_other = "DOMESTIC_OTHER"  # other rate -> box 1c
    private_use = "PRIVATE_USE"  # -> box 1d
    domestic_zero_or_exempt = "DOMESTIC_ZERO_OR_EXEMPT"  # -> box 1e
    exempt = "EXEMPT"  # -> box 1e, no deductible input VAT on the purchase side
    domestic_reverse_charge_received = "DOMESTIC_REVERSE_CHARGE_RECEIVED"  # -> box 2a
    export_non_eu = "EXPORT_NON_EU"  # -> box 3a
    eu_supply = "EU_SUPPLY"  # -> box 3b
    eu_distance_sale = "EU_DISTANCE_SALE"  # -> box 3c
    import_non_eu = "IMPORT_NON_EU"  # -> box 4a
    eu_acquisition = "EU_ACQUISITION"  # -> box 4b


class InputVatEligibility(str, enum.Enum):
    eligible = "ELIGIBLE"
    ineligible = "INELIGIBLE"
    partially_eligible = "PARTIALLY_ELIGIBLE"
    requires_review = "REQUIRES_REVIEW"


class TransactionApprovalStatus(str, enum.Enum):
    draft = "DRAFT"
    approved = "APPROVED"
    locked = "LOCKED"


class VatReturnStatus(str, enum.Enum):
    draft = "draft"
    needs_review = "needs_review"
    ready_for_approval = "ready_for_approval"
    approved = "approved"
    locked = "locked"


class NoteType(str, enum.Enum):
    internal = "INTERNAL"
    customer_question = "CUSTOMER_QUESTION"
    missing_document_request = "MISSING_DOCUMENT_REQUEST"


class NoteStatus(str, enum.Enum):
    open = "OPEN"
    answered = "ANSWERED"
    resolved = "RESOLVED"


class BatchStatus(str, enum.Enum):
    processing = "processing"
    completed = "completed"


class BankSourceFormat(str, enum.Enum):
    camt053 = "CAMT053"
    camt054 = "CAMT054"
    mt940 = "MT940"
    csv = "CSV"
    open_banking = "OPEN_BANKING"  # Phase 12: synced via a provider, not a file


class BankConsentStatus(str, enum.Enum):
    """Open Banking connection status. Phase 12 adds a real provider
    abstraction (app/services/open_banking_provider.py) and a stub
    provider for development -- no authorised AISP agreement/credentials
    exist for this project, so `connected` only ever reflects the stub in
    this build. See docs/open-banking.md."""

    not_connected = "NOT_CONNECTED"
    pending = "PENDING"  # consent flow started, not yet completed
    connected = "CONNECTED"
    expired = "EXPIRED"  # consent lapsed (PSD2 RTS: max 90 days), needs renewal
    error = "ERROR"
    revoked = "REVOKED"


class ReconciliationStatus(str, enum.Enum):
    imported = "IMPORTED"
    unmatched = "UNMATCHED"
    suggested_match = "SUGGESTED_MATCH"
    matched = "MATCHED"
    partially_matched = "PARTIALLY_MATCHED"
    manually_reconciled = "MANUALLY_RECONCILED"
    excluded = "EXCLUDED"


class MatchConfidence(str, enum.Enum):
    high = "HIGH"
    medium = "MEDIUM"
    low = "LOW"
    none = "NONE"


class MatchStatus(str, enum.Enum):
    suggested = "SUGGESTED"
    approved = "APPROVED"
    rejected = "REJECTED"
    reversed = "REVERSED"


class RecurringFrequency(str, enum.Enum):
    weekly = "WEEKLY"
    monthly = "MONTHLY"
    quarterly = "QUARTERLY"
    annual = "ANNUAL"


class RecurringStatus(str, enum.Enum):
    active = "ACTIVE"
    missing = "MISSING"
    stopped = "STOPPED"


class CategorySource(str, enum.Enum):
    rule = "RULE"
    ai_suggested = "AI_SUGGESTED"
    manual = "MANUAL"


class CategorizationRuleType(str, enum.Enum):
    supplier_name = "SUPPLIER_NAME"
    iban = "IBAN"
    description_pattern = "DESCRIPTION_PATTERN"


class AnomalySeverity(str, enum.Enum):
    info = "info"
    warning = "warning"
    critical = "critical"


class AnomalyStatus(str, enum.Enum):
    open = "OPEN"
    acknowledged = "ACKNOWLEDGED"
    dismissed = "DISMISSED"


class ReportPeriodType(str, enum.Enum):
    monthly = "MONTHLY"
    quarterly = "QUARTERLY"
    annual = "ANNUAL"
    custom = "CUSTOM"


class BalanceSheetItemCategory(str, enum.Enum):
    """Manually-entered balance-sheet items -- this ledger has no chart of
    accounts, so fixed assets/equity/loans/inventory are never derived or
    guessed, only recorded explicitly by an accountant."""

    fixed_assets = "FIXED_ASSETS"
    inventory = "INVENTORY"
    other_asset = "OTHER_ASSET"
    equity = "EQUITY"
    loans = "LOANS"
    other_liability = "OTHER_LIABILITY"


class BudgetStatus(str, enum.Enum):
    draft = "DRAFT"
    submitted = "SUBMITTED"
    approved = "APPROVED"


class BudgetLineSource(str, enum.Enum):
    manual = "MANUAL"
    ai_suggested = "AI_SUGGESTED"


class ScenarioType(str, enum.Enum):
    base = "BASE"
    optimistic = "OPTIMISTIC"
    conservative = "CONSERVATIVE"
    custom = "CUSTOM"


class LegalFormCode(str, enum.Enum):
    eenmanszaak = "EENMANSZAAK"
    vof = "VOF"
    maatschap = "MAATSCHAP"
    cv = "CV"
    bv = "BV"
    nv = "NV"
    cooperatie = "COOPERATIE"
    owm = "OWM"
    stichting = "STICHTING"
    vereniging = "VERENIGING"
    vve = "VVE"
    rederij = "REDERIJ"
    other = "OTHER"


class LiabilityType(str, enum.Enum):
    unlimited_personal = "UNLIMITED_PERSONAL"
    limited = "LIMITED"
    shared_unlimited = "SHARED_UNLIMITED"
    mixed = "MIXED"


class PartnerType(str, enum.Enum):
    general = "GENERAL"
    limited = "LIMITED"


class EmploymentType(str, enum.Enum):
    permanent = "PERMANENT"
    fixed_term = "FIXED_TERM"
    zero_hours = "ZERO_HOURS"
    on_call = "ON_CALL"


class SalaryBasis(str, enum.Enum):
    monthly = "MONTHLY"
    hourly = "HOURLY"


class PayrollPeriodType(str, enum.Enum):
    monthly = "MONTHLY"
    four_weekly = "FOUR_WEEKLY"


class PayrollRunStatus(str, enum.Enum):
    draft = "DRAFT"
    approved = "APPROVED"
    paid = "PAID"
    corrected = "CORRECTED"


class TimesheetEntryType(str, enum.Enum):
    worked = "WORKED"
    holiday = "HOLIDAY"
    sick = "SICK"
    absence = "ABSENCE"


class TimesheetStatus(str, enum.Enum):
    draft = "DRAFT"
    submitted = "SUBMITTED"
    approved = "APPROVED"
    rejected = "REJECTED"


class TaxOpportunityRisk(str, enum.Enum):
    low = "LOW"
    medium = "MEDIUM"
    high = "HIGH"


class TaxCentreItemStatus(str, enum.Enum):
    prepared = "PREPARED"
    under_review = "UNDER_REVIEW"
    approved = "APPROVED"
    filed = "FILED"
    paid = "PAID"
    overdue = "OVERDUE"


class LoonheffingenDeclarationStatus(str, enum.Enum):
    draft = "DRAFT"
    validation = "VALIDATION"
    accountant_review = "ACCOUNTANT_REVIEW"
    approved = "APPROVED"
    ready_for_submission = "READY_FOR_SUBMISSION"
    submitted = "SUBMITTED"
    accepted = "ACCEPTED"
    rejected = "REJECTED"

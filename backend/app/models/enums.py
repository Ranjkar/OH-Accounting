import enum


class UserRole(str, enum.Enum):
    admin = "admin"
    accountant = "accountant"
    viewer = "viewer"
    customer = "customer"


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

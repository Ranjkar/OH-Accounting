import enum


class UserRole(str, enum.Enum):
    admin = "admin"
    accountant = "accountant"
    viewer = "viewer"


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
    unknown = "UNKNOWN"


class ValidationSeverity(str, enum.Enum):
    info = "info"
    warning = "warning"
    error = "error"


class ProcessingAttemptStatus(str, enum.Enum):
    running = "running"
    succeeded = "succeeded"
    failed = "failed"

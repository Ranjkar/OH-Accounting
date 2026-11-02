from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.enums import (
    AnomalySeverity,
    AnomalyStatus,
    CategorizationRuleType,
    CategorySource,
    RecurringFrequency,
    RecurringStatus,
)


class CategorizationRuleCreate(BaseModel):
    company_id: int
    rule_type: CategorizationRuleType
    match_value: str
    category: str


class CategorizationRuleOut(BaseModel):
    id: int
    company_id: int
    rule_type: CategorizationRuleType
    match_value: str
    category: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CategorizeTransactionRequest(BaseModel):
    category: str
    remember_as_rule: bool = False


class CategorySuggestionOut(BaseModel):
    suggested_category: str
    confidence: float
    reasoning: str
    evidence: list[str]
    requires_accountant_review: bool


class TransactionCategoryOut(BaseModel):
    transaction_id: int
    expense_category: str | None
    category_confidence: Decimal | None
    category_source: CategorySource | None


class RecurringPatternOut(BaseModel):
    id: int
    company_id: int
    counterparty_name: str | None
    counterparty_iban: str | None
    frequency: RecurringFrequency
    expected_amount: Decimal
    last_transaction_date: date
    next_expected_date: date
    status: RecurringStatus
    occurrence_count: int

    model_config = ConfigDict(from_attributes=True)


class AnomalyFlagOut(BaseModel):
    id: int
    company_id: int
    rule_code: str
    severity: AnomalySeverity
    message: str
    evidence: dict
    related_entity_type: str
    related_entity_id: int
    status: AnomalyStatus
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AutomationCentreSummary(BaseModel):
    company_id: int
    unmatched_transactions: int
    suggested_matches: int
    high_confidence_suggested_matches: int
    missing_invoices_estimate: int
    expenses_awaiting_categorization: int
    open_anomalies: int
    recurring_missing: int
    failed_import_batches: int
    pending_notes: int

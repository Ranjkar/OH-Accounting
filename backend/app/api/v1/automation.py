from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.accounting import anomaly_detection, categorization, recurring_detection
from app.core.deps import get_current_user, require_company_access, require_editor
from app.db.session import get_db
from app.models.accounting import AccountingTransaction
from app.models.anomaly import AnomalyFlag
from app.models.banking import BankImportBatch, BankTransaction
from app.models.categorization import CategorizationRule
from app.models.company import Company
from app.models.note import AccountantNote
from app.models.recurring import RecurringPattern
from app.models.enums import (
    AnomalyStatus,
    NoteStatus,
    ReconciliationStatus,
    RecurringStatus,
)
from app.models.user import User
from app.schemas.automation import (
    AnomalyFlagOut,
    AutomationCentreSummary,
    CategorizationRuleCreate,
    CategorizationRuleOut,
    CategorizeTransactionRequest,
    CategorySuggestionOut,
    RecurringPatternOut,
)
from app.services.ai_categorization_provider import get_categorization_provider

router = APIRouter(tags=["automation"])


def _get_company_or_404(db: Session, user: User, company_id: int) -> Company:
    require_company_access(company_id, user, db)
    company = db.get(Company, company_id)
    if company is None or company.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return company


# ---- Expense categorization ----


@router.post("/categorization-rules", response_model=CategorizationRuleOut, status_code=status.HTTP_201_CREATED)
def create_categorization_rule(payload: CategorizationRuleCreate, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    company = _get_company_or_404(db, user, payload.company_id)
    rule = CategorizationRule(
        tenant_id=user.tenant_id, company_id=company.id, rule_type=payload.rule_type,
        match_value=payload.match_value, category=payload.category, created_by_user_id=user.id,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.get("/categorization-rules", response_model=list[CategorizationRuleOut])
def list_categorization_rules(company_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _get_company_or_404(db, user, company_id)
    return db.query(CategorizationRule).filter(CategorizationRule.company_id == company_id).all()


@router.get("/transactions/{transaction_id}/category-suggestion", response_model=CategorySuggestionOut)
def suggest_category(transaction_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tx = db.get(AccountingTransaction, transaction_id)
    if tx is None or tx.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    require_company_access(tx.company_id, user, db)

    provider = get_categorization_provider()
    suggestion = provider.suggest_category(tx.counterparty_name, tx.accounting_classification, str(tx.net_amount))
    return CategorySuggestionOut(**suggestion.model_dump())


@router.post("/transactions/{transaction_id}/categorize", response_model=dict)
def categorize_transaction(
    transaction_id: int, payload: CategorizeTransactionRequest, db: Session = Depends(get_db), user: User = Depends(require_editor)
):
    from app.models.enums import CategorySource

    tx = db.get(AccountingTransaction, transaction_id)
    if tx is None or tx.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    require_company_access(tx.company_id, user, db)

    tx.expense_category = payload.category
    tx.category_source = CategorySource.manual
    tx.category_confidence = None

    rule_created = None
    if payload.remember_as_rule:
        rule = categorization.create_rule_from_correction(db, tx, payload.category, user.id)
        rule_created = rule.id if rule else None

    db.commit()
    return {"transaction_id": tx.id, "expense_category": tx.expense_category, "rule_created_id": rule_created}


@router.post("/companies/{company_id}/apply-categorization-rules", response_model=dict)
def apply_categorization_rules(company_id: int, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    _get_company_or_404(db, user, company_id)
    transactions = (
        db.query(AccountingTransaction)
        .filter(AccountingTransaction.company_id == company_id, AccountingTransaction.expense_category.is_(None))
        .all()
    )
    applied = 0
    for tx in transactions:
        if categorization.apply_rules(db, tx):
            applied += 1
    db.commit()
    return {"transactions_checked": len(transactions), "rules_applied": applied}


# ---- Recurring detection ----


@router.post("/companies/{company_id}/detect-recurring", response_model=list[RecurringPatternOut])
def detect_recurring(company_id: int, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    company = _get_company_or_404(db, user, company_id)
    patterns = recurring_detection.detect_recurring_patterns(db, company.id, company.tenant_id)
    db.commit()
    return patterns


@router.get("/companies/{company_id}/recurring-patterns", response_model=list[RecurringPatternOut])
def list_recurring_patterns(company_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _get_company_or_404(db, user, company_id)
    return db.query(RecurringPattern).filter(RecurringPattern.company_id == company_id).all()


# ---- Anomaly detection ----


@router.post("/companies/{company_id}/detect-anomalies", response_model=list[AnomalyFlagOut])
def detect_anomalies(company_id: int, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    company = _get_company_or_404(db, user, company_id)
    flags = anomaly_detection.run_all_rules(db, company.id, company.tenant_id)
    db.commit()
    return flags


@router.get("/companies/{company_id}/anomalies", response_model=list[AnomalyFlagOut])
def list_anomalies(company_id: int, status_filter: AnomalyStatus | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _get_company_or_404(db, user, company_id)
    query = db.query(AnomalyFlag).filter(AnomalyFlag.company_id == company_id)
    if status_filter is not None:
        query = query.filter(AnomalyFlag.status == status_filter)
    return query.order_by(AnomalyFlag.created_at.desc()).all()


@router.post("/anomalies/{anomaly_id}/acknowledge", response_model=AnomalyFlagOut)
def acknowledge_anomaly(anomaly_id: int, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    from datetime import datetime, timezone

    flag = db.get(AnomalyFlag, anomaly_id)
    if flag is None or flag.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anomaly not found")
    require_company_access(flag.company_id, user, db)
    flag.status = AnomalyStatus.acknowledged
    flag.acknowledged_by_user_id = user.id
    flag.acknowledged_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(flag)
    return flag


@router.post("/anomalies/{anomaly_id}/dismiss", response_model=AnomalyFlagOut)
def dismiss_anomaly(anomaly_id: int, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    flag = db.get(AnomalyFlag, anomaly_id)
    if flag is None or flag.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anomaly not found")
    require_company_access(flag.company_id, user, db)
    flag.status = AnomalyStatus.dismissed
    db.commit()
    db.refresh(flag)
    return flag


# ---- Automation centre dashboard ----


@router.get("/companies/{company_id}/automation-centre", response_model=AutomationCentreSummary)
def automation_centre_summary(company_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _get_company_or_404(db, user, company_id)

    unmatched = db.query(BankTransaction).filter(BankTransaction.company_id == company_id, BankTransaction.reconciliation_status == ReconciliationStatus.unmatched).count()
    suggested = db.query(BankTransaction).filter(BankTransaction.company_id == company_id, BankTransaction.reconciliation_status == ReconciliationStatus.suggested_match).count()

    from app.models.banking import PaymentMatch

    high_confidence_suggested = (
        db.query(PaymentMatch)
        .filter(PaymentMatch.company_id == company_id, PaymentMatch.status == "SUGGESTED", PaymentMatch.confidence_level == "HIGH")
        .count()
    )

    missing_invoices_estimate = unmatched  # unmatched incoming/outgoing bank activity with no corresponding invoice yet

    awaiting_categorization = (
        db.query(AccountingTransaction)
        .filter(AccountingTransaction.company_id == company_id, AccountingTransaction.expense_category.is_(None))
        .count()
    )
    open_anomalies = db.query(AnomalyFlag).filter(AnomalyFlag.company_id == company_id, AnomalyFlag.status == AnomalyStatus.open).count()
    recurring_missing = db.query(RecurringPattern).filter(RecurringPattern.company_id == company_id, RecurringPattern.status == RecurringStatus.missing).count()
    failed_imports = db.query(BankImportBatch).filter(BankImportBatch.company_id == company_id, BankImportBatch.error_count > 0).count()
    pending_notes = db.query(AccountantNote).filter(AccountantNote.company_id == company_id, AccountantNote.status != NoteStatus.resolved).count()

    return AutomationCentreSummary(
        company_id=company_id,
        unmatched_transactions=unmatched,
        suggested_matches=suggested,
        high_confidence_suggested_matches=high_confidence_suggested,
        missing_invoices_estimate=missing_invoices_estimate,
        expenses_awaiting_categorization=awaiting_categorization,
        open_anomalies=open_anomalies,
        recurring_missing=recurring_missing,
        failed_import_batches=failed_imports,
        pending_notes=pending_notes,
    )


@router.get("/companies/{company_id}/cash-flow-forecast")
def cash_flow_forecast(company_id: int, months_ahead: int = 3, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.accounting.cash_flow import build_cash_flow_forecast

    _get_company_or_404(db, user, company_id)
    return build_cash_flow_forecast(db, company_id, months_ahead)

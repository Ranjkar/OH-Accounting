from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.accounting.completeness import assess_period
from app.core.deps import get_current_user, require_company_access, require_editor
from app.db.session import get_db
from app.models.accounting import AccountingTransaction, Payment, VatReturn
from app.models.audit_log import AuditLog
from app.models.company import Company
from app.models.document import Document
from app.models.enums import DocumentStatus, LedgerSide, NoteStatus, NoteType, TransactionType, UserRole
from app.models.financial_year import FinancialYear
from app.models.note import AccountantNote
from app.models.user import User
from app.schemas.note import NoteCreate, NoteStatusUpdate
from app.schemas.workspace import CompanyWorkspace, NoteOut, PeriodCompleteness

router = APIRouter(tags=["workspace"])


@router.get("/companies/{company_id}/workspace", response_model=CompanyWorkspace)
def get_company_workspace(company_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_company_access(company_id, user, db)
    company = db.get(Company, company_id)
    if company is None or company.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    financial_years = db.query(FinancialYear).filter(FinancialYear.company_id == company_id).all()
    transactions = db.query(AccountingTransaction).filter(AccountingTransaction.company_id == company_id).all()
    sales_invoice_count = sum(1 for t in transactions if t.transaction_type == TransactionType.sales_invoice)
    purchase_invoice_count = sum(1 for t in transactions if t.transaction_type == TransactionType.purchase_invoice)
    payment_count = db.query(Payment).filter(Payment.company_id == company_id).count()
    document_count = db.query(Document).filter(Document.company_id == company_id).count()
    documents_awaiting_approval = (
        db.query(Document)
        .filter(Document.company_id == company_id, Document.status.in_([DocumentStatus.extracted, DocumentStatus.needs_review]))
        .count()
    )

    notes = (
        db.query(AccountantNote)
        .filter(AccountantNote.company_id == company_id)
        .order_by(AccountantNote.created_at.desc())
        .all()
    )
    open_notes = sum(1 for n in notes if n.status == NoteStatus.open and n.note_type == NoteType.internal)
    open_customer_questions = sum(
        1 for n in notes if n.status != NoteStatus.resolved and n.note_type in (NoteType.customer_question, NoteType.missing_document_request)
    )

    period_completeness: list[PeriodCompleteness] = []
    vat_returns_out: list[dict] = []
    for fy in financial_years:
        for period in fy.vat_periods:
            vat_return = db.query(VatReturn).filter(VatReturn.vat_period_id == period.id).first()
            rows = assess_period(db, company_id, period, vat_return.status if vat_return else None)
            period_completeness.append(
                PeriodCompleteness(
                    vat_period_id=period.id,
                    label=f"{fy.year} {period.label}",
                    start_date=period.start_date,
                    end_date=period.end_date,
                    filing_deadline=period.filing_deadline,
                    vat_return_status=vat_return.status if vat_return else None,
                    rows=[{"requirement": r.requirement, "complete": r.complete, "detail": r.detail} for r in rows],
                )
            )
            if vat_return:
                vat_returns_out.append(
                    {
                        "id": vat_return.id,
                        "vat_period_id": period.id,
                        "period_label": f"{fy.year} {period.label}",
                        "status": vat_return.status.value,
                        "net_payable": str(vat_return.net_payable),
                    }
                )

    return CompanyWorkspace(
        company_id=company.id,
        company_name=company.name,
        vat_frequency=company.vat_frequency.value,
        vat_accounting_basis=company.vat_accounting_basis.value,
        financial_year_count=len(financial_years),
        sales_invoice_count=sales_invoice_count,
        purchase_invoice_count=purchase_invoice_count,
        transaction_count=len(transactions),
        payment_count=payment_count,
        document_count=document_count,
        documents_awaiting_approval=documents_awaiting_approval,
        open_notes=open_notes,
        open_customer_questions=open_customer_questions,
        vat_returns=vat_returns_out,
        period_completeness=period_completeness,
        notes=notes,
    )


@router.get("/companies/{company_id}/notes", response_model=list[NoteOut])
def list_notes(company_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_company_access(company_id, user, db)
    return (
        db.query(AccountantNote)
        # Phase 17.1 (audit MEDIUM-1): the tenant predicate was missing and
        # `require_company_access` used to no-op for owner/admin, so any
        # authenticated user in any tenant -- including a read-only `viewer`
        # -- could read another firm's free-text accountant notes about a
        # client. The three sibling endpoints in this file were already
        # correct; only this one was missed. Defence-in-depth on top of the
        # now-authoritative helper.
        .filter(AccountantNote.tenant_id == user.tenant_id, AccountantNote.company_id == company_id)
        .order_by(AccountantNote.created_at.desc())
        .all()
    )


@router.post("/companies/{company_id}/notes", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
def create_note(
    company_id: int, payload: NoteCreate, db: Session = Depends(get_db), user: User = Depends(require_editor)
):
    require_company_access(company_id, user, db)
    company = db.get(Company, company_id)
    if company is None or company.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    note = AccountantNote(
        tenant_id=user.tenant_id,
        company_id=company_id,
        author_user_id=user.id,
        note_type=payload.note_type,
        body=payload.body,
        related_entity_type=payload.related_entity_type,
        related_entity_id=payload.related_entity_id,
    )
    db.add(note)
    db.flush()
    db.add(
        AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action="create",
            entity_type="accountant_note",
            entity_id=note.id,
            after={"note_type": payload.note_type.value, "body": payload.body},
        )
    )
    db.commit()
    db.refresh(note)
    return note


@router.patch("/notes/{note_id}/status", response_model=NoteOut)
def update_note_status(
    note_id: int, payload: NoteStatusUpdate, db: Session = Depends(get_db), user: User = Depends(require_editor)
):
    note = db.get(AccountantNote, note_id)
    if note is None or note.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    require_company_access(note.company_id, user, db)

    before_status = note.status.value
    note.status = payload.status
    if payload.status == NoteStatus.resolved:
        note.resolved_at = datetime.now(timezone.utc)
    db.add(
        AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action="update_status",
            entity_type="accountant_note",
            entity_id=note.id,
            before={"status": before_status},
            after={"status": payload.status.value},
        )
    )
    db.commit()
    db.refresh(note)
    return note

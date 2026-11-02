from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.accounting import assistant_facts, scenario_engine
from app.core.config import settings
from app.core.deps import get_current_user, require_company_access
from app.db.session import get_db
from app.models.accounting import VatReturn
from app.models.company import Company
from app.models.financial_year import VatPeriod
from app.models.user import User
from app.schemas.assistant import AssistantQuestion, AssistantResponse
from app.schemas.financial_question import FinancialQuestion
from app.services import ai_assistant_provider

router = APIRouter(prefix="/assistant", tags=["assistant"])


def _get_company(db: Session, user: User, company_id: int) -> Company:
    require_company_access(company_id, user, db)
    company = db.get(Company, company_id)
    if company is None or company.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return company


def _respond(facts: dict, question: str) -> AssistantResponse:
    provider = ai_assistant_provider.get_assistant_provider()
    answer = provider.ask(facts, question)
    return AssistantResponse(facts=facts, answer=answer, model=settings.anthropic_model, generated_at=datetime.now(timezone.utc))


@router.post("/ask", response_model=AssistantResponse)
def ask(payload: AssistantQuestion, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    company = _get_company(db, user, payload.company_id)
    facts = assistant_facts.company_facts(db, company)
    if payload.vat_period_id is not None:
        vat_return = db.query(VatReturn).filter(VatReturn.vat_period_id == payload.vat_period_id).first()
        if vat_return is not None:
            facts["vat_return"] = assistant_facts.vat_return_facts(db, vat_return)
    return _respond(facts, payload.question)


@router.get("/company-summary", response_model=AssistantResponse)
def company_summary(company_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    company = _get_company(db, user, company_id)
    facts = assistant_facts.company_facts(db, company)
    return _respond(facts, "Summarize this company's current financial position and flag anything that needs the accountant's attention.")


@router.get("/vat-return-explanation/{vat_return_id}", response_model=AssistantResponse)
def vat_return_explanation(vat_return_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    vat_return = db.get(VatReturn, vat_return_id)
    if vat_return is None or vat_return.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="VAT return not found")
    require_company_access(vat_return.company_id, user, db)
    facts = assistant_facts.vat_return_facts(db, vat_return)
    return _respond(
        facts,
        "Explain how this VAT return's total was calculated, in plain English, box by box. "
        "Mention any pending documents, duplicates, or validation errors that should be resolved first.",
    )


@router.get("/missing-documents", response_model=AssistantResponse)
def missing_documents(company_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    company = _get_company(db, user, company_id)
    facts = assistant_facts.missing_documents_facts(db, company)
    return _respond(facts, "List what documents or corrections are still needed from this client, and why, in a short bulleted list.")


@router.get("/period-comparison", response_model=AssistantResponse)
def period_comparison(
    company_id: int,
    vat_period_id_a: int,
    vat_period_id_b: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    company = _get_company(db, user, company_id)
    period_a = db.get(VatPeriod, vat_period_id_a)
    period_b = db.get(VatPeriod, vat_period_id_b)
    if period_a is None or period_b is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="VAT period not found")
    facts = assistant_facts.period_comparison_facts(db, company, period_a, period_b)
    return _respond(
        facts,
        "Compare these two periods and explain the key differences in sales, purchases, and VAT payable. "
        "If either period is not yet final (is_final is false), say so clearly.",
    )


@router.post("/financial-question", response_model=AssistantResponse)
def financial_question(payload: FinancialQuestion, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Covers Phase 8's financial-intelligence questions ("how profitable
    was my business this quarter", "why did expenses increase", "which
    customers have overdue invoices", "how does this year compare with last
    year", "what is my estimated tax liability"). For a what-if question
    ("what happens if revenue falls by 15%"), pass scenario_assumptions and
    the pre-computed scenario result is added to FACTS -- the AI still only
    narrates numbers app.accounting.scenario_engine already calculated."""
    company = _get_company(db, user, payload.company_id)
    facts = assistant_facts.financial_intelligence_facts(
        db, company, payload.period_type, payload.reference_date or date.today(), payload.custom_start, payload.custom_end
    )
    if payload.scenario_assumptions:
        from app.api.v1._json_safe import to_json_safe

        facts["requested_scenario"] = to_json_safe(
            scenario_engine.apply_scenario(db, company.id, payload.scenario_assumptions, horizon_months=3, reference_date=payload.reference_date or date.today())
        )
    return _respond(facts, payload.question)

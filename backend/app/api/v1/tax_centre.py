from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.accounting import dutch_tax_rules as tax
from app.accounting import entity_tax, structure_comparator, tax_optimization
from app.api.v1._json_safe import to_json_safe
from app.core.deps import get_current_user, require_company_access
from app.models.accounting import VatReturn
from app.db.session import get_db
from app.models.company import Company
from app.models.employee import Employee
from app.models.enums import LegalFormCode, SalaryBasis, VatReturnStatus
from app.models.legal_form import CompanyLegalForm, Partner
from app.models.user import User

router = APIRouter(prefix="/tax-centre", tags=["tax-centre"])

_VAT_STATUS_TO_CENTRE_STATUS = {
    VatReturnStatus.draft: "PREPARED",
    VatReturnStatus.needs_review: "UNDER_REVIEW",
    VatReturnStatus.ready_for_approval: "UNDER_REVIEW",
    VatReturnStatus.approved: "APPROVED",
    VatReturnStatus.locked: "FILED",
}


def _get_company_or_404(db: Session, user: User, company_id: int) -> Company:
    require_company_access(company_id, user, db)
    company = db.get(Company, company_id)
    if company is None or company.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return company


def _current_legal_form(db: Session, company_id: int, as_of: date) -> LegalFormCode | None:
    row = (
        db.query(CompanyLegalForm)
        .filter(CompanyLegalForm.company_id == company_id, CompanyLegalForm.effective_from <= as_of)
        .filter((CompanyLegalForm.effective_to.is_(None)) | (CompanyLegalForm.effective_to > as_of))
        .order_by(CompanyLegalForm.effective_from.desc())
        .first()
    )
    return row.legal_form_code if row else None


@router.get("/overview")
def tax_centre_overview(company_id: int, as_of_date: date | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """BTW/ICP/OSS status reuses the existing VAT engine's own VatReturn
    rows -- no second VAT tracking system. Corporate/income tax rows are
    estimates only until this system actually has a filing integration."""
    company = _get_company_or_404(db, user, company_id)
    as_of = as_of_date or date.today()
    legal_form = _current_legal_form(db, company.id, as_of)

    vat_returns = db.query(VatReturn).filter(VatReturn.company_id == company.id).all()

    vat_rows = [
        {
            "category": "BTW",
            "period_label": r.vat_period.label,
            "status": _VAT_STATUS_TO_CENTRE_STATUS.get(r.status, "PREPARED"),
            "net_payable": r.net_payable,
            "filing_deadline": r.vat_period.filing_deadline,
            "payment_deadline": r.vat_period.payment_deadline,
        }
        for r in vat_returns
    ]

    return to_json_safe(
        {
            "company_id": company.id,
            "company_name": company.name,
            "as_of_date": as_of,
            "current_legal_form": legal_form.value if legal_form else None,
            "legal_form_warning": None if legal_form else "No legal form has been recorded for this company -- set one via /company-legal-forms before relying on any tax estimate here.",
            "btw": vat_rows,
            "icp": {"status": "NOT_TRACKED", "note": "ICP (intra-community transactions listing) is not yet a separate tracked declaration -- the underlying EU-supply transactions are visible in the VAT overview (box 3b)."},
            "oss": {"status": "NOT_TRACKED", "note": "OSS (One Stop Shop, for EU distance sales) is not yet a separate tracked declaration -- the underlying transactions are visible in the VAT overview (box 3c)."},
            "income_tax": {"status": "NOT_FILED", "note": "Use /tax-centre/income-tax-estimate for an estimate -- no filing integration exists."},
            "corporate_income_tax": {"status": "NOT_FILED", "note": "Use /tax-centre/corporate-tax-estimate for an estimate -- no filing integration exists."},
            "payroll_tax": {"status": "NOT_FILED", "note": "See the Loonheffingen module -- no filing integration exists."},
            "sbr_digipoort_integration_status": "NOT_CONNECTED -- architecture-only, see docs/sbr-digipoort-integration.md. No submission is ever claimed as filed without a real, authorised, verified connection.",
        }
    )


@router.get("/income-tax-estimate")
def income_tax_estimate(
    company_id: int, annual_profit: Decimal, hours_criterion_met: bool = False, is_starter: bool = False,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    _get_company_or_404(db, user, company_id)
    rules = tax.get_rule_set()
    legal_form = _current_legal_form(db, company_id, date.today())
    if legal_form is not None and legal_form not in (LegalFormCode.eenmanszaak, LegalFormCode.vof, LegalFormCode.maatschap, LegalFormCode.cv):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{legal_form.value} is not subject to personal income tax on business profit in the way this endpoint estimates -- see /tax-centre/corporate-tax-estimate instead")

    partners = db.query(Partner).filter(Partner.company_id == company_id, Partner.effective_to.is_(None)).all()
    if partners:
        allocation = entity_tax.allocate_vof_profit(
            annual_profit,
            [{"name": p.name, "profit_share_percentage": p.profit_share_percentage, "hours_criterion_met": p.entrepreneur_hours_eligible, "is_starter": False} for p in partners],
        )
        return to_json_safe({"legal_form": legal_form.value if legal_form else None, "per_partner": allocation})

    return to_json_safe(entity_tax.estimate_sole_proprietor_income_tax(annual_profit, hours_criterion_met, is_starter, rules))


@router.get("/corporate-tax-estimate")
def corporate_tax_estimate(company_id: int, annual_taxable_profit: Decimal, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _get_company_or_404(db, user, company_id)
    return to_json_safe(entity_tax.estimate_bv_corporate_tax(annual_taxable_profit))


def _highest_non_dga_employee_annual_salary(db: Session, company_id: int) -> Decimal | None:
    """Annualizes each non-DGA employee's pay (monthly_salary * 12, or
    hourly_rate * contracted_hours_per_week * 52 for hourly staff -- an
    approximation, since actual hours worked can differ from contracted
    hours) and returns the highest figure, or None if no comparable
    employee data is on file. Never includes an employee flagged is_dga."""
    employees = (
        db.query(Employee)
        .filter(Employee.company_id == company_id, Employee.is_dga.is_(False), Employee.employment_end_date.is_(None))
        .all()
    )
    annual_salaries = []
    for employee in employees:
        if employee.salary_basis == SalaryBasis.monthly and employee.monthly_salary:
            annual_salaries.append(employee.monthly_salary * 12)
        elif employee.salary_basis == SalaryBasis.hourly and employee.hourly_rate and employee.contracted_hours_per_week:
            annual_salaries.append(employee.hourly_rate * employee.contracted_hours_per_week * 52)
    return max(annual_salaries) if annual_salaries else None


@router.get("/dga-position")
def dga_position(
    company_id: int, proposed_dga_salary: Decimal, dividend_declared: Decimal = Decimal("0"),
    comparable_role_salary: Decimal | None = None, highest_employee_salary: Decimal | None = None,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    _get_company_or_404(db, user, company_id)
    auto_filled = False
    if highest_employee_salary is None:
        highest_employee_salary = _highest_non_dga_employee_annual_salary(db, company_id)
        auto_filled = highest_employee_salary is not None
    result = entity_tax.estimate_dga_position(proposed_dga_salary, comparable_role_salary, highest_employee_salary, dividend_declared)
    result["highest_employee_salary_auto_filled"] = auto_filled
    if auto_filled:
        result["salary_check"]["note_on_highest_employee_salary"] = (
            "highest_employee_salary was auto-filled from this company's highest-paid non-DGA, currently-employed "
            "employee record (annualized from monthly_salary, or hourly_rate x contracted_hours_per_week x 52 for "
            "hourly staff) -- pass the query parameter explicitly to override if that employee is not actually "
            "comparable, or if the underlying data is stale."
        )
    return to_json_safe(result)


@router.get("/tax-optimization")
def tax_optimization_opportunities(
    company_id: int, annual_profit: Decimal | None = None, annual_revenue: Decimal | None = None,
    hours_criterion_met: bool = False, is_starter: bool = False,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    _get_company_or_404(db, user, company_id)
    legal_form = _current_legal_form(db, company_id, date.today())
    opportunities = tax_optimization.find_opportunities(
        legal_form_code=legal_form.value if legal_form else "OTHER", annual_profit=annual_profit, annual_revenue=annual_revenue,
        hours_criterion_met=hours_criterion_met, is_starter=is_starter,
    )
    return to_json_safe([vars(o) for o in opportunities])


@router.get("/structure-comparison")
def structure_comparison(
    company_id: int, annual_revenue: Decimal, annual_operating_expenses: Decimal,
    hours_criterion_met: bool = True, is_starter: bool = False, num_partners: int = 1,
    dga_salary: Decimal | None = None, dividend_declared: Decimal = Decimal("0"),
    partner_shares: str | None = Query(None, description="Comma-separated percentages, e.g. 60,40"),
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    _get_company_or_404(db, user, company_id)
    shares = [Decimal(s) for s in partner_shares.split(",")] if partner_shares else None
    assumptions = structure_comparator.StructureAssumptions(
        annual_revenue=annual_revenue, annual_operating_expenses=annual_operating_expenses,
        hours_criterion_met=hours_criterion_met, is_starter=is_starter, num_partners=num_partners,
        partner_profit_shares=shares, dga_salary=dga_salary, dividend_declared=dividend_declared,
    )
    return to_json_safe(structure_comparator.compare_structures(assumptions))

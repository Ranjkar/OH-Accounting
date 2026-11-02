from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_company_access
from app.db.session import get_db
from app.models.accounting import VatReturn
from app.models.company import Company
from app.models.financial_year import FinancialYear
from app.models.user import User
from app.reporting import financial_report, vat_report

router = APIRouter(prefix="/reports", tags=["reports"])

CONTENT_TYPES = {
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv",
}


def _get_company(db: Session, user: User, company_id: int) -> Company:
    require_company_access(company_id, user, db)
    company = db.get(Company, company_id)
    if company is None or company.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return company


def _render(fmt: str, filename: str, renderers: dict) -> Response:
    if fmt not in renderers:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported format: {fmt}")
    content = renderers[fmt]()
    return Response(
        content=content,
        media_type=CONTENT_TYPES[fmt],
        headers={"Content-Disposition": f'attachment; filename="{filename}.{fmt}"'},
    )


@router.get("/vat-return/{vat_return_id}")
def vat_return_report(
    vat_return_id: int, format: str = "pdf", db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    vat_return = db.get(VatReturn, vat_return_id)
    if vat_return is None or vat_return.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="VAT return not found")
    company = _get_company(db, user, vat_return.company_id)

    data = vat_report.build_vat_report_data(db, vat_return, company)
    return _render(
        format,
        f"vat-return-{company.id}-{vat_return.vat_period_id}",
        {
            "pdf": lambda: vat_report.render_pdf(data),
            "xlsx": lambda: vat_report.render_xlsx(data),
            "csv": lambda: vat_report.render_csv(data),
        },
    )


@router.get("/financial-overview")
def financial_overview_report(
    company_id: int,
    financial_year_id: int,
    format: str = "pdf",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    company = _get_company(db, user, company_id)
    financial_year = db.get(FinancialYear, financial_year_id)
    if financial_year is None or financial_year.company_id != company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Financial year not found")

    data = financial_report.build_financial_overview_data(db, company, financial_year)
    return _render(
        format,
        f"financial-overview-{company.id}-{financial_year.year}",
        {
            "pdf": lambda: financial_report.render_pdf(data),
            "xlsx": lambda: financial_report.render_xlsx(data),
            "csv": lambda: financial_report.render_csv(data),
        },
    )


@router.get("/period-comparison")
def period_comparison_json(
    company_id: int,
    financial_year_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """JSON data for the frontend's period-comparison view (same underlying
    computation as the financial overview report, without rendering a file)."""
    company = _get_company(db, user, company_id)
    financial_year = db.get(FinancialYear, financial_year_id)
    if financial_year is None or financial_year.company_id != company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Financial year not found")

    data = financial_report.build_financial_overview_data(db, company, financial_year)
    return {
        "financial_year": financial_year.year,
        "periods": [
            {
                "label": p["label"],
                "sales_net": str(p["sales_net"]),
                "purchases_net": str(p["purchases_net"]),
                "income_minus_expense": str(p["income_minus_expense"]),
                "transaction_count": p["transaction_count"],
            }
            for p in data["periods_summary"]
        ],
        "total_sales_net": str(data["total_sales_net"]),
        "total_purchases_net": str(data["total_purchases_net"]),
        "net_income": str(data["net_income"]),
        "payment_status_counts": data["payment_status_counts"],
    }

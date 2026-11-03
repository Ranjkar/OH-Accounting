from fastapi import APIRouter

from app.api.v1 import (
    assistant,
    auth,
    automation,
    banking,
    batches,
    budgets,
    companies,
    dashboard,
    documents,
    employees,
    financial_reports,
    forecasts,
    legal_forms,
    loonheffingen,
    payroll,
    reports,
    tax_calendar,
    tax_centre,
    transactions,
    vat_returns,
    workspace,
)

router = APIRouter()
router.include_router(auth.router)
router.include_router(companies.router)
router.include_router(dashboard.router)
router.include_router(documents.router)
router.include_router(batches.router)
router.include_router(transactions.router)
router.include_router(vat_returns.router)
router.include_router(workspace.router)
router.include_router(tax_calendar.router)
router.include_router(assistant.router)
router.include_router(reports.router)
router.include_router(banking.router)
router.include_router(automation.router)
router.include_router(financial_reports.router)
router.include_router(budgets.router)
router.include_router(forecasts.router)
router.include_router(legal_forms.router)
router.include_router(employees.router)
router.include_router(payroll.router)
router.include_router(loonheffingen.router)
router.include_router(tax_centre.router)

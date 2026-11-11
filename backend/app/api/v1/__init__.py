from fastapi import APIRouter

from app.api.v1 import (
    assistant,
    audit_log,
    auth,
    automation,
    banking,
    batches,
    billing,
    budgets,
    companies,
    company_setup,
    contracts,
    dashboard,
    documents,
    email_admin,
    employee_self_service,
    employees,
    financial_reports,
    forecasts,
    kvk,
    legal_forms,
    loonheffingen,
    payroll,
    reports,
    tax_calendar,
    tax_centre,
    transactions,
    users,
    vat_returns,
    workspace,
)

router = APIRouter()
router.include_router(auth.router)
# company_setup's literal "/companies/setup-drafts" must register BEFORE
# companies' parameterised "/companies/{company_id}" (same ordering rule
# users.py documents for its /invitations routes).
router.include_router(company_setup.router)
router.include_router(companies.router)
router.include_router(email_admin.router)
router.include_router(contracts.router)
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
router.include_router(employee_self_service.router)
router.include_router(payroll.router)
router.include_router(loonheffingen.router)
router.include_router(tax_centre.router)
router.include_router(kvk.router)
router.include_router(billing.router)
router.include_router(users.router)
router.include_router(audit_log.router)

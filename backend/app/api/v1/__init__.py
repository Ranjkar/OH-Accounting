from fastapi import APIRouter

from app.api.v1 import (
    assistant,
    auth,
    batches,
    companies,
    dashboard,
    documents,
    reports,
    tax_calendar,
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

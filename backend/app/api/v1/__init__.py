from fastapi import APIRouter

from app.api.v1 import auth, companies, dashboard, documents, transactions, vat_returns

router = APIRouter()
router.include_router(auth.router)
router.include_router(companies.router)
router.include_router(dashboard.router)
router.include_router(documents.router)
router.include_router(transactions.router)
router.include_router(vat_returns.router)

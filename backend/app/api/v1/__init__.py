from fastapi import APIRouter

from app.api.v1 import auth, companies, dashboard, documents

router = APIRouter()
router.include_router(auth.router)
router.include_router(companies.router)
router.include_router(dashboard.router)
router.include_router(documents.router)

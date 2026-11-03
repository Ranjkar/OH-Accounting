import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_company_access
from app.db.session import get_db
from app.models.company import Company
from app.models.user import User
from app.services.kvk_provider import KvkNotFoundError, get_kvk_provider

router = APIRouter(prefix="/kvk", tags=["kvk"])


def _normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


@router.get("/lookup/{kvk_number}")
def lookup_company(kvk_number: str, user: User = Depends(get_current_user)):
    """Looks up a company by KVK number via the official KVK API
    (developers.kvk.nl) -- never scrapes the Handelsregister. Defaults to
    KVK's own published test sandbox; is_test_data in the response says
    so explicitly rather than presenting sandbox data as a real lookup.
    See docs/government-integrations.md."""
    provider = get_kvk_provider()
    try:
        result = provider.lookup_basisprofiel(kvk_number)
    except KvkNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return result.to_dict()


@router.get("/verify/{company_id}")
def verify_company(company_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Cross-checks this company's own stored name against the KVK record
    for its stored kvk_number -- a lightweight "is this still the company
    we think it is" check, not a replacement for KVK's own verification
    product. Name comparison is case/punctuation-insensitive substring
    matching, not a fuzzy/AI match, so the result is deterministic and
    reproducible."""
    require_company_access(company_id, user, db)
    company = db.get(Company, company_id)
    if company is None or company.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    if not company.kvk_number:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This company has no KVK number on file to verify against")

    provider = get_kvk_provider()
    try:
        result = provider.lookup_basisprofiel(company.kvk_number)
    except KvkNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    stored_name = _normalize_name(company.name)
    kvk_name = _normalize_name(result.name)
    name_matches = stored_name in kvk_name or kvk_name in stored_name

    return {
        "company_id": company.id,
        "stored_name": company.name,
        "kvk_name": result.name,
        "kvk_number": result.kvk_number,
        "name_matches": name_matches,
        "is_test_data": result.is_test_data,
        "legal_form": result.legal_form,
        "address": result.address,
    }

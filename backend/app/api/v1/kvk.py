from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import get_current_user
from app.models.user import User
from app.services.kvk_provider import KvkNotFoundError, get_kvk_provider

router = APIRouter(prefix="/kvk", tags=["kvk"])


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

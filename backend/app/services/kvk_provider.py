"""KVK (Dutch Chamber of Commerce) company lookup provider abstraction.

Uses the official KVK API (developers.kvk.nl) -- never scrapes the
Handelsregister, which KVK's own terms explicitly reserve to itself
(Databankenwet). Defaults to KVK's own published TEST environment
(api.kvk.nl/test/...) with KVK's own published, non-secret test API key
(documented openly at developers.kvk.nl/documentation/testing) -- this
is a real, working sandbox verified by fetching it directly this
session, not invented. Switching to production requires an explicit
KVK_API_BASE_URL + a real paid KVK_API_KEY from a signed KVK agreement;
this module never silently promotes itself to production.
"""

import logging
from typing import Protocol

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# KVK's own published sandbox base URL and test API key (not a secret --
# KVK documents this key publicly for anyone to use against test data).
KVK_TEST_BASE_URL = "https://api.kvk.nl/test/api/v1"
KVK_TEST_API_KEY = "l7xx1f2691f2520d487b902f4e0b57a0b197"


class KvkLookupResult:
    def __init__(self, kvk_number: str, name: str, legal_form: str | None, trade_names: list[str], address: str | None, sbi_activity: str | None, is_test_data: bool):
        self.kvk_number = kvk_number
        self.name = name
        self.legal_form = legal_form
        self.trade_names = trade_names
        self.address = address
        self.sbi_activity = sbi_activity
        self.is_test_data = is_test_data

    def to_dict(self) -> dict:
        return {
            "kvk_number": self.kvk_number,
            "name": self.name,
            "legal_form": self.legal_form,
            "trade_names": self.trade_names,
            "address": self.address,
            "sbi_activity": self.sbi_activity,
            "is_test_data": self.is_test_data,
        }


class KvkNotFoundError(Exception):
    pass


class KvkProvider(Protocol):
    def lookup_basisprofiel(self, kvk_number: str) -> KvkLookupResult: ...


class HttpKvkProvider:
    """Real KVK API client. Against the test base URL by default -- see
    module docstring. is_test_data is always True when base_url is the
    KVK-published test environment, so callers (and the API response)
    never present sandbox data as if it were a real lookup."""

    def __init__(self, base_url: str, api_key: str):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._is_test = self._base_url == KVK_TEST_BASE_URL

    def lookup_basisprofiel(self, kvk_number: str) -> KvkLookupResult:
        response = httpx.get(
            f"{self._base_url}/basisprofielen/{kvk_number}",
            headers={"apikey": self._api_key},
            timeout=10.0,
        )
        if response.status_code == 404:
            raise KvkNotFoundError(f"No KVK record found for {kvk_number}")
        response.raise_for_status()
        data = response.json()

        owner = data.get("_embedded", {}).get("eigenaar", {})
        hoofdvestiging = data.get("_embedded", {}).get("hoofdvestiging", {})
        address = None
        for a in hoofdvestiging.get("adressen", []):
            if a.get("type") == "bezoekadres":
                address = a.get("volledigAdres")
                break
        sbi_list = data.get("sbiActiviteiten", [])
        sbi_activity = next((s.get("sbiOmschrijving") for s in sbi_list if s.get("indHoofdactiviteit") == "Ja"), None)

        return KvkLookupResult(
            kvk_number=data.get("kvkNummer", kvk_number),
            name=data.get("naam", ""),
            legal_form=owner.get("rechtsvorm"),
            trade_names=[h.get("naam") for h in data.get("handelsnamen", []) if h.get("naam")],
            address=address,
            sbi_activity=sbi_activity,
            is_test_data=self._is_test,
        )


_provider: KvkProvider | None = None


def get_kvk_provider() -> KvkProvider:
    global _provider
    if _provider is not None:
        return _provider
    base_url = settings.kvk_api_base_url or KVK_TEST_BASE_URL
    api_key = settings.kvk_api_key or KVK_TEST_API_KEY
    _provider = HttpKvkProvider(base_url, api_key)
    return _provider


def reset_provider_cache() -> None:
    """Test hook: clear the cached provider singleton."""
    global _provider
    _provider = None

"""Electronic-signature provider adapter (Phase 26).

eIDAS (Regulation (EU) 910/2014) distinguishes three levels:
  * SIMPLE electronic signature (art. 3(10)) -- data attached to other data
    used by the signatory to sign. This is what the built-in provider
    produces: possession of an emailed secret link, a typed legal name and
    an explicit consent checkbox, evidenced by timestamps and the document
    hash. Legally admissible in NL (art. 3:15a BW) but identity assurance
    rests on the e-mail channel only.
  * ADVANCED (art. 26) -- uniquely linked to and capable of identifying the
    signatory, created under their sole control, tamper-evident.
  * QUALIFIED (art. 3(12)) -- advanced + qualified certificate + qualified
    signature creation device, issued by a trust-service provider on the EU
    trusted list. Legal equivalent of a handwritten signature.

This module does NOT provide advanced or qualified signatures. The Protocol
exists so a trust-service provider adapter can be plugged in later via
CONTRACTS_SIGNING_PROVIDER; until one exists, no UI text may describe the
result as advanced or qualified.
"""

from dataclasses import dataclass
from typing import Protocol

from app.core.config import settings


@dataclass
class SignatureRequest:
    contract_reference: str
    document_sha256: str
    signer_name_typed: str
    signer_email: str
    consent_text: str


@dataclass
class SignatureResult:
    signing_method: str  # recorded on ContractSignature.signing_method
    provider_name: str
    provider_reference: str | None = None
    assurance_level: str = "simple"  # simple | advanced | qualified


class SigningProvider(Protocol):
    name: str

    def sign(self, request: SignatureRequest) -> SignatureResult: ...


class InternalSimpleSignatureProvider:
    """Records the evidence captured by our own signing page. No external
    call, no certificate: the assurance is the emailed link + typed name."""

    name = "internal"

    def sign(self, request: SignatureRequest) -> SignatureResult:
        return SignatureResult(signing_method="simple_electronic_typed_name", provider_name=self.name, assurance_level="simple")


_provider: SigningProvider | None = None


def get_signing_provider() -> SigningProvider:
    global _provider
    if _provider is None:
        kind = (settings.contracts_signing_provider or "internal").strip().lower()
        if kind != "internal":
            raise RuntimeError(f"CONTRACTS_SIGNING_PROVIDER={kind!r} is not supported (only 'internal' exists)")
        _provider = InternalSimpleSignatureProvider()
    return _provider


def reset_provider_cache() -> None:
    global _provider
    _provider = None

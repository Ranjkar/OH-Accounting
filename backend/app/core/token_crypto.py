"""Symmetric encryption for Open Banking access/refresh tokens at rest.
Deliberately a SEPARATE key and module from app/core/crypto.py's BSN
encryption (which documents itself as "never used for anything else") --
a compromised Open Banking key must never also expose BSNs, and vice
versa. Same MultiFernet rotation pattern as crypto.py (see
docs/encryption-key-rotation.md), applied to a different secret class."""

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.core.config import settings


def _fernet() -> MultiFernet:
    keys = [settings.open_banking_token_encryption_key] + [
        k for k in settings.open_banking_token_encryption_key_previous.split(",") if k.strip()
    ]
    return MultiFernet([Fernet(k.encode()) for k in keys])


def encrypt_token(raw_token: str) -> bytes:
    return _fernet().encrypt(raw_token.encode())


def decrypt_token(token: bytes) -> str:
    try:
        return _fernet().decrypt(token).decode()
    except InvalidToken as exc:
        raise ValueError("Token could not be decrypted -- wrong key(s) or corrupted data") from exc

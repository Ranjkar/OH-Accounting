"""Symmetric encryption for BSN-at-rest. Never used for anything else.
A BSN is never passed to the AI assistant or written to a log -- callers
must decrypt only at the point of display to an authorised payroll user,
never earlier."""

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def _fernet() -> Fernet:
    return Fernet(settings.bsn_encryption_key.encode())


def encrypt_bsn(bsn: str) -> bytes:
    return _fernet().encrypt(bsn.encode())


def decrypt_bsn(token: bytes) -> str:
    try:
        return _fernet().decrypt(token).decode()
    except InvalidToken as exc:
        raise ValueError("BSN could not be decrypted -- wrong key or corrupted data") from exc


def mask_bsn(bsn: str) -> str:
    digits = "".join(c for c in bsn if c.isdigit())
    if len(digits) <= 3:
        return "*" * len(digits)
    return "*" * (len(digits) - 3) + digits[-3:]

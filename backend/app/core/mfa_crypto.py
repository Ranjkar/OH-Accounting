"""Symmetric encryption for TOTP MFA secrets at rest. Deliberately a
SEPARATE key and module from app/core/crypto.py (BSN) and
app/core/token_crypto.py (Open Banking tokens) -- a compromised MFA key
must never also expose BSNs or bank tokens, and vice versa. Same
MultiFernet rotation pattern as those modules (see
docs/encryption-key-rotation.md), applied to a third secret class."""

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.core.config import settings


def _fernet() -> MultiFernet:
    keys = [settings.mfa_secret_encryption_key] + [
        k for k in settings.mfa_secret_encryption_key_previous.split(",") if k.strip()
    ]
    return MultiFernet([Fernet(k.encode()) for k in keys])


def encrypt_mfa_secret(raw_secret: str) -> bytes:
    return _fernet().encrypt(raw_secret.encode())


def decrypt_mfa_secret(token: bytes) -> str:
    try:
        return _fernet().decrypt(token).decode()
    except InvalidToken as exc:
        raise ValueError("MFA secret could not be decrypted -- wrong key(s) or corrupted data") from exc

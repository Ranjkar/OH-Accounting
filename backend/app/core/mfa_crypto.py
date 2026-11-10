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


def reencrypt_mfa_secret_with_current_key(token: bytes) -> bytes:
    """Decrypts with whichever key (current or previous) matches, then
    re-encrypts with only the current key.

    Phase 17.4 (audit 7.5): this function did not exist, although the module
    docstring already claimed the "same MultiFernet rotation pattern" as the
    other two crypto modules. Without it a compromised MFA key could never be
    retired -- and an MFA key is the most security-critical of the three,
    since anyone who can decrypt a TOTP seed can generate valid codes
    indefinitely and bypass MFA completely rather than merely read data.
    Driven by scripts/rotate_encryption_keys.py."""
    return _fernet().rotate(token)

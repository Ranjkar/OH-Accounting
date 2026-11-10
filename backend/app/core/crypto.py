"""Symmetric encryption for BSN-at-rest. Never used for anything else.
A BSN is never passed to the AI assistant or written to a log -- callers
must decrypt only at the point of display to an authorised payroll user,
never earlier.

Uses MultiFernet so a key rotation can run safely: new values always
encrypt with the first (current) key in bsn_encryption_key, while
decryption also accepts any key listed in bsn_encryption_key_previous --
old ciphertext keeps working until it is explicitly re-encrypted. See
docs/encryption-key-rotation.md for the full rotation procedure; this
module never rotates a key on its own."""

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.core.config import settings


def _fernet() -> MultiFernet:
    keys = [settings.bsn_encryption_key] + [k for k in settings.bsn_encryption_key_previous.split(",") if k.strip()]
    return MultiFernet([Fernet(k.encode()) for k in keys])


def encrypt_bsn(bsn: str) -> bytes:
    return _fernet().encrypt(bsn.encode())


def decrypt_bsn(token: bytes) -> str:
    try:
        return _fernet().decrypt(token).decode()
    except InvalidToken as exc:
        raise ValueError("BSN could not be decrypted -- wrong key(s) or corrupted data") from exc


def reencrypt_bsn_with_current_key(token: bytes) -> bytes:
    """Decrypts with whichever key (current or previous) matches, then
    re-encrypts with only the current key -- used by the key-rotation
    script to migrate existing ciphertext off a retired key."""
    return _fernet().rotate(token)


def mask_bsn(bsn: str) -> str:
    digits = "".join(c for c in bsn if c.isdigit())
    if len(digits) <= 3:
        return "*" * len(digits)
    return "*" * (len(digits) - 3) + digits[-3:]

"""RFC 6238 TOTP, stdlib only (hmac/hashlib/base64/struct) -- no new
dependency for a well-defined ~20-line algorithm. Used for optional
per-user MFA; see app/core/mfa_crypto.py for secret-at-rest encryption."""

import base64
import hashlib
import hmac
import secrets
import struct
import time

_STEP_SECONDS = 30
_DIGITS = 6


def generate_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _code_for_counter(secret_b32: str, counter: int) -> str:
    padded = secret_b32 + "=" * (-len(secret_b32) % 8)
    key = base64.b32decode(padded, casefold=True)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code_int = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % (10**_DIGITS)
    return str(code_int).zfill(_DIGITS)


def totp_code(secret_b32: str, for_time: float | None = None) -> str:
    counter = int((for_time if for_time is not None else time.time()) // _STEP_SECONDS)
    return _code_for_counter(secret_b32, counter)


def verify_code(secret_b32: str, code: str, for_time: float | None = None, window: int = 1) -> bool:
    """Accepts the code for the current step and `window` steps on either
    side, to tolerate clock drift between server and authenticator app."""
    now = for_time if for_time is not None else time.time()
    counter = int(now // _STEP_SECONDS)
    code = code.strip()
    return any(hmac.compare_digest(_code_for_counter(secret_b32, counter + offset), code) for offset in range(-window, window + 1))


def provisioning_uri(secret_b32: str, account_email: str, issuer: str = "OnHolland Accounting") -> str:
    from urllib.parse import quote

    label = quote(f"{issuer}:{account_email}")
    return f"otpauth://totp/{label}?secret={secret_b32}&issuer={quote(issuer)}&digits={_DIGITS}&period={_STEP_SECONDS}"


def _demo() -> None:
    secret = generate_secret()
    now = 1_700_000_000.0
    code = totp_code(secret, for_time=now)
    assert verify_code(secret, code, for_time=now)
    assert verify_code(secret, code, for_time=now + 29)
    assert not verify_code(secret, code, for_time=now + 200)
    assert not verify_code(secret, "000000", for_time=now) or code == "000000"
    assert "otpauth://totp/" in provisioning_uri(secret, "user@example.com")


if __name__ == "__main__":
    _demo()
    print("ok")

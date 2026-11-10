import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return pwd_context.verify(password, hashed_password)


def create_access_token(subject: str, token_version: int) -> str:
    """token_version is the user's CURRENT version at issue time, embedded
    as the "ver" claim. Logging out (or any future forced-revocation path)
    bumps the user's stored version, which immediately invalidates every
    token issued before the bump -- checked in app.core.deps."""
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {"sub": subject, "ver": token_version, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> tuple[str, int] | None:
    """Returns (email, token_version) from a valid, unexpired token, or
    None. Callers must still compare token_version against the user's
    current stored value -- this function only proves the token itself is
    well-formed and unexpired, not that it hasn't been revoked."""
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        sub = payload.get("sub")
        if sub is None:
            return None
        return sub, int(payload.get("ver", 0))
    except JWTError:
        return None


def generate_password_reset_token() -> tuple[str, str]:
    """Returns (raw_token, token_hash). The raw token goes in the one-time
    email/link and is never stored; only its SHA-256 hash is persisted
    (app.models.password_reset.PasswordResetToken), same principle as
    never storing a plaintext password."""
    raw_token = secrets.token_urlsafe(32)
    return raw_token, hash_reset_token(raw_token)


def hash_reset_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()

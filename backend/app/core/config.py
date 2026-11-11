import logging

from pydantic import Field
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

INSECURE_DEFAULT_JWT_SECRET = "dev-secret-change-in-production"
INSECURE_DEFAULT_BSN_ENCRYPTION_KEY = "lKDqZ0RFLmPlasPurAMcQxGNT6KlIu5X3cT41UC8ei4="
INSECURE_DEFAULT_OPEN_BANKING_KEY = "lFMlxrHVoe19oQjvmkuASRr2LnY3zeEVhA8ewJYBwd4="
INSECURE_DEFAULT_MFA_SECRET_KEY = "JEOzBUqvIIQwzP6uIzI0T3AJrTAeh5Rfg-3KFUcoEfg="
INSECURE_DEFAULT_BILLING_WEBHOOK_SECRET = "UPvKGVEfZNpj7zknwoIA95LrniZGjKNSyZhTlUI7l0k"

# backend/.env.example has always shipped this literal for JWT_SECRET, which
# is NOT the same string as INSECURE_DEFAULT_JWT_SECRET above. An operator who
# copied the template into .env.prod would therefore have sailed straight past
# a check that only compared against the code default -- while running a
# publicly-known JWT signing key. Both values are guarded.
INSECURE_TEMPLATE_JWT_SECRET = "change-me-in-production"

# Phase 17.4 (audit 6.4). Only these values are treated as "local, throwaway,
# the committed placeholder keys are acceptable here". EVERYTHING else --
# including a typo like "prodction" or an unset-but-renamed value -- fails
# closed, because failing open on a secret check is the one failure mode this
# guard must never have.
PERMISSIVE_ENVIRONMENTS = frozenset({"development", "dev", "test", "testing"})


class Settings(BaseSettings):
    # Phase 17.4 (audit 6.4): selects whether the insecure-placeholder secret
    # check below warns (local development) or refuses to start (everywhere
    # else). Set ENVIRONMENT=production in docker-compose.prod.yml. There is
    # deliberately no "staging is exempt" tier -- anything that is not local
    # development must carry real secrets.
    environment: str = "development"

    # repr=False: the production DATABASE_URL embeds POSTGRES_PASSWORD.
    database_url: str = Field(
        default="postgresql+psycopg://sam@localhost:5432/onholland_accounting", repr=False
    )
    # Phase 17.4: every secret below is declared with repr=False.
    #
    # pydantic-settings renders a plain-`str` field in `repr(settings)`, so
    # before this an f-string, a debug log, an exception context, or pytest's
    # own fixture dump would print all five secrets verbatim. (This was found
    # for real: a failing test's fixture repr printed a configured webhook
    # secret into the console.) `repr=False` removes them from the
    # representation without changing how any consumer reads the value.
    jwt_secret: str = Field(default=INSECURE_DEFAULT_JWT_SECRET, repr=False)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24

    anthropic_api_key: str | None = Field(default=None, repr=False)
    anthropic_model: str = "claude-sonnet-5"
    storage_root: str = "./storage"
    max_upload_size_bytes: int = 20 * 1024 * 1024
    extraction_confidence_threshold: float = 0.7

    # Bulk batch processing: bounded worker pool, no Celery/Redis. Tune these
    # for Claude's actual rate limits rather than firing every doc at once.
    batch_max_concurrency: int = 3
    batch_max_files: int = 100
    claude_max_retries: int = 3
    claude_retry_base_delay_seconds: float = 2.0

    # Sensitive-endpoint in-memory rate limiting (single process -- resets on
    # restart, not shared across workers; move to a shared store if the app
    # is ever run with multiple worker processes).
    rate_limit_login_per_minute: int = 10
    rate_limit_upload_per_minute: int = 30

    # Symmetric encryption key (Fernet) for BSN-at-rest. Never used for
    # anything else, never logged, never sent to the AI assistant.
    bsn_encryption_key: str = Field(default=INSECURE_DEFAULT_BSN_ENCRYPTION_KEY, repr=False)
    # Comma-separated OLDER keys, newest-last-used-first: still accepted for
    # decryption during a rotation (see app.core.crypto, MultiFernet), never
    # used to encrypt new values. Empty until a rotation is in progress.
    # See docs/encryption-key-rotation.md for the full procedure.
    bsn_encryption_key_previous: str = Field(default="", repr=False)

    # Phase 12: KVK (Chamber of Commerce) company lookup. Defaults to KVK's
    # own published test sandbox + test key (see app.services.kvk_provider)
    # when unset -- never silently defaults to production.
    kvk_api_key: str | None = Field(default=None, repr=False)
    kvk_api_base_url: str | None = None

    # Phase 12: Open Banking access/refresh token encryption (separate key
    # from BSN encryption -- see app.core.token_crypto).
    open_banking_token_encryption_key: str = Field(default=INSECURE_DEFAULT_OPEN_BANKING_KEY, repr=False)
    open_banking_token_encryption_key_previous: str = Field(default="", repr=False)

    # Phase 12: how long a password-reset link stays valid, and how many
    # consecutive failed logins trigger a temporary account lock.
    password_reset_token_expire_minutes: int = 30
    max_failed_login_attempts: int = 5
    account_lockout_minutes: int = 15

    # Phase 13: TOTP MFA secret encryption (separate key again -- see
    # app.core.mfa_crypto -- a compromised MFA key must never also expose
    # BSNs or Open Banking tokens, and vice versa).
    mfa_secret_encryption_key: str = Field(default=INSECURE_DEFAULT_MFA_SECRET_KEY, repr=False)
    mfa_secret_encryption_key_previous: str = Field(default="", repr=False)

    # Phase 14: billing webhook signature verification (sandbox stub
    # provider only, see app.services.billing_provider). Not a payment
    # credential -- it only authenticates that a webhook really came from
    # the configured billing provider.
    billing_webhook_secret: str = Field(default=INSECURE_DEFAULT_BILLING_WEBHOOK_SECRET, repr=False)

    # ---- Phase 22: outbound email (app/services/email_provider.py) ----
    # EMAIL_PROVIDER selects the transport: "none" (default -- nothing is sent,
    # every message is logged to email_outbox as "failed: no provider", and
    # invitation/reset links are shown in the UI instead), "smtp", or
    # "resend" (https://resend.com transactional API). Credentials are only
    # ever read here; no API response ever includes them.
    email_provider: str = "none"
    email_from_address: str = "no-reply@localhost"
    email_from_name: str = "OnHolland Accounting"
    # Public origin of the frontend, used to build links in emails
    # (password reset, verification, invitations). Must be https in prod.
    app_base_url: str = "http://localhost:3000"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = Field(default=None, repr=False)
    smtp_password: str | None = Field(default=None, repr=False)
    smtp_use_tls: bool = True  # STARTTLS on 587; set False with smtp_use_ssl for implicit TLS on 465
    smtp_use_ssl: bool = False
    resend_api_key: str | None = Field(default=None, repr=False)
    email_max_attempts: int = 3
    email_retry_base_delay_seconds: float = 1.0
    # Abuse guard: max messages per recipient per hour, and per tenant per hour.
    email_rate_limit_per_recipient_per_hour: int = 10
    email_rate_limit_per_tenant_per_hour: int = 200

    # ---- Phase 22: Open Banking provider selection ----
    # "stub" is the only adapter that exists (see docs/open-banking.md). Any
    # other value refuses to start rather than silently falling back to
    # synthetic data while an operator believes a real bank is connected.
    open_banking_provider: str = "stub"

    class Config:
        env_file = ".env"


settings = Settings()

# Phase 17.4 (audit 6.4). Each entry is (settings attribute, environment
# variable name, tuple of unacceptable values, remediation hint).
#
# This table holds NAMES, known-bad literals that are already public in this
# repository, and hints. Nothing here, and nothing in the warning or the
# exception below, ever renders a secret the operator actually configured --
# a secret check that leaks the secret it is checking would be worse than no
# check at all.
_GUARDED_SECRETS: tuple[tuple[str, str, tuple[str, ...], str], ...] = (
    (
        "jwt_secret",
        "JWT_SECRET",
        (INSECURE_DEFAULT_JWT_SECRET, INSECURE_TEMPLATE_JWT_SECRET),
        "Anyone holding this value can forge an access token for any user in any "
        "tenant, including owner and platform-admin accounts. Generate one with: "
        "python -c 'import secrets; print(secrets.token_urlsafe(48))'",
    ),
    (
        "bsn_encryption_key",
        "BSN_ENCRYPTION_KEY",
        (INSECURE_DEFAULT_BSN_ENCRYPTION_KEY,),
        "Employee BSNs would be encrypted under a key that is committed to this "
        "repository, so anyone with database or backup read access can decrypt "
        "every one of them. Generate one with: "
        "python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'",
    ),
    (
        "open_banking_token_encryption_key",
        "OPEN_BANKING_TOKEN_ENCRYPTION_KEY",
        (INSECURE_DEFAULT_OPEN_BANKING_KEY,),
        "Bank access/refresh tokens would be encrypted under a committed key. "
        "Generate one with: "
        "python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'",
    ),
    (
        "mfa_secret_encryption_key",
        "MFA_SECRET_ENCRYPTION_KEY",
        (INSECURE_DEFAULT_MFA_SECRET_KEY,),
        "TOTP secrets would be encrypted under a committed key, so anyone with "
        "database read access could decrypt them and generate valid codes -- "
        "defeating MFA entirely rather than weakening it. Generate one with: "
        "python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'",
    ),
    (
        "billing_webhook_secret",
        "BILLING_WEBHOOK_SECRET",
        (INSECURE_DEFAULT_BILLING_WEBHOOK_SECRET,),
        "Webhook HMAC signatures could be forged, allowing any tenant's "
        "subscription status to be flipped at will. Inert while the billing "
        "provider is the sandbox stub, but it must be real before one is "
        "connected. Generate one with: "
        "python -c 'import secrets; print(secrets.token_urlsafe(32))'",
    ),
)


def insecure_placeholder_secrets() -> list[tuple[str, str]]:
    """[(environment variable name, remediation hint)] for every guarded
    secret that is unset, blank, or still on a value that is public in this
    repository.

    Exported (not private) so tests, an operator's pre-flight check and
    scripts/rotate_encryption_keys.py can all assert on one definition of
    "not good enough". Returns names and hints only, never values."""
    offenders: list[tuple[str, str]] = []
    for attr, env_name, unacceptable, hint in _GUARDED_SECRETS:
        value = getattr(settings, attr)
        # Blank counts as an offence too: `JWT_SECRET=` in an env file yields
        # an empty string, and an empty HMAC signing key or Fernet key is far
        # worse than a placeholder -- it would not even be caught by a
        # "does this equal the known-bad value" comparison.
        if not str(value).strip() or str(value) in unacceptable:
            offenders.append((env_name, hint))
    return offenders


def _enforce_secret_hygiene() -> None:
    offenders = insecure_placeholder_secrets()
    if not offenders:
        return

    if settings.environment.strip().lower() in PERMISSIVE_ENVIRONMENTS:
        for env_name, hint in offenders:
            logger.warning("%s is still the insecure placeholder value. %s", env_name, hint)
        return

    names = ", ".join(env_name for env_name, _ in offenders)
    detail = "\n".join(f"  - {env_name}: {hint}" for env_name, hint in offenders)
    raise RuntimeError(
        f"Refusing to start: ENVIRONMENT={settings.environment!r} but these secrets are unset, "
        f"blank, or still a value that is public in this repository: {names}.\n\n{detail}\n\n"
        "Set each one in the environment or the deployment's .env.prod. This check fails closed on "
        "purpose. The previous behaviour only logged a warning, so a deployment that forgot these "
        "variables booted successfully, passed /health, and encrypted real BSNs, Open Banking "
        "tokens and MFA secrets under keys that are public in this repository. See "
        "docs/QWEN_TECHNICAL_AUDIT_REPORT.md section 6.4 and docs/PHASE_17_SECURITY_REMEDIATION.md."
    )


_enforce_secret_hygiene()

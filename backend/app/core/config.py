import logging

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

INSECURE_DEFAULT_JWT_SECRET = "dev-secret-change-in-production"
INSECURE_DEFAULT_BSN_ENCRYPTION_KEY = "lKDqZ0RFLmPlasPurAMcQxGNT6KlIu5X3cT41UC8ei4="
INSECURE_DEFAULT_OPEN_BANKING_KEY = "lFMlxrHVoe19oQjvmkuASRr2LnY3zeEVhA8ewJYBwd4="
INSECURE_DEFAULT_MFA_SECRET_KEY = "JEOzBUqvIIQwzP6uIzI0T3AJrTAeh5Rfg-3KFUcoEfg="
INSECURE_DEFAULT_BILLING_WEBHOOK_SECRET = "UPvKGVEfZNpj7zknwoIA95LrniZGjKNSyZhTlUI7l0k"


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://sam@localhost:5432/onholland_accounting"
    jwt_secret: str = INSECURE_DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24

    anthropic_api_key: str | None = None
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
    bsn_encryption_key: str = INSECURE_DEFAULT_BSN_ENCRYPTION_KEY
    # Comma-separated OLDER keys, newest-last-used-first: still accepted for
    # decryption during a rotation (see app.core.crypto, MultiFernet), never
    # used to encrypt new values. Empty until a rotation is in progress.
    # See docs/encryption-key-rotation.md for the full procedure.
    bsn_encryption_key_previous: str = ""

    # Phase 12: KVK (Chamber of Commerce) company lookup. Defaults to KVK's
    # own published test sandbox + test key (see app.services.kvk_provider)
    # when unset -- never silently defaults to production.
    kvk_api_key: str | None = None
    kvk_api_base_url: str | None = None

    # Phase 12: Open Banking access/refresh token encryption (separate key
    # from BSN encryption -- see app.core.token_crypto).
    open_banking_token_encryption_key: str = INSECURE_DEFAULT_OPEN_BANKING_KEY
    open_banking_token_encryption_key_previous: str = ""

    # Phase 12: how long a password-reset link stays valid, and how many
    # consecutive failed logins trigger a temporary account lock.
    password_reset_token_expire_minutes: int = 30
    max_failed_login_attempts: int = 5
    account_lockout_minutes: int = 15

    # Phase 13: TOTP MFA secret encryption (separate key again -- see
    # app.core.mfa_crypto -- a compromised MFA key must never also expose
    # BSNs or Open Banking tokens, and vice versa).
    mfa_secret_encryption_key: str = INSECURE_DEFAULT_MFA_SECRET_KEY
    mfa_secret_encryption_key_previous: str = ""

    # Phase 14: billing webhook signature verification (sandbox stub
    # provider only, see app.services.billing_provider). Not a payment
    # credential -- it only authenticates that a webhook really came from
    # the configured billing provider.
    billing_webhook_secret: str = INSECURE_DEFAULT_BILLING_WEBHOOK_SECRET

    class Config:
        env_file = ".env"


settings = Settings()

if settings.jwt_secret == INSECURE_DEFAULT_JWT_SECRET:
    logger.warning(
        "JWT_SECRET is still the insecure placeholder value. Set a strong, randomly generated "
        "JWT_SECRET in the environment before this is reachable from anywhere but localhost."
    )

if settings.bsn_encryption_key == INSECURE_DEFAULT_BSN_ENCRYPTION_KEY:
    logger.warning(
        "BSN_ENCRYPTION_KEY is still the insecure placeholder value. Set a strong, randomly "
        "generated Fernet key (cryptography.fernet.Fernet.generate_key()) in the environment "
        "before any real employee BSN is ever stored."
    )

if settings.open_banking_token_encryption_key == INSECURE_DEFAULT_OPEN_BANKING_KEY:
    logger.warning(
        "OPEN_BANKING_TOKEN_ENCRYPTION_KEY is still the insecure placeholder value. Set a strong, "
        "randomly generated Fernet key in the environment before any real bank access/refresh "
        "token is ever stored."
    )

if settings.mfa_secret_encryption_key == INSECURE_DEFAULT_MFA_SECRET_KEY:
    logger.warning(
        "MFA_SECRET_ENCRYPTION_KEY is still the insecure placeholder value. Set a strong, "
        "randomly generated Fernet key in the environment before any real user enrolls in MFA."
    )

if settings.billing_webhook_secret == INSECURE_DEFAULT_BILLING_WEBHOOK_SECRET:
    logger.warning(
        "BILLING_WEBHOOK_SECRET is still the insecure placeholder value. This only matters once "
        "a real billing provider is connected (none is, see docs/subscription-billing.md) -- "
        "set a strong secret before that happens."
    )

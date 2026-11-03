import logging

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

INSECURE_DEFAULT_JWT_SECRET = "dev-secret-change-in-production"
INSECURE_DEFAULT_BSN_ENCRYPTION_KEY = "lKDqZ0RFLmPlasPurAMcQxGNT6KlIu5X3cT41UC8ei4="


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

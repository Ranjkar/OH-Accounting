import logging

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

INSECURE_DEFAULT_JWT_SECRET = "dev-secret-change-in-production"


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

    class Config:
        env_file = ".env"


settings = Settings()

if settings.jwt_secret == INSECURE_DEFAULT_JWT_SECRET:
    logger.warning(
        "JWT_SECRET is still the insecure placeholder value. Set a strong, randomly generated "
        "JWT_SECRET in the environment before this is reachable from anywhere but localhost."
    )

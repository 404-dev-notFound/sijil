from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App configuration, loaded from environment variables / .env.local.

    Fields with no default are required — instantiating Settings() without them raises
    a validation error immediately on startup, per architecture doc Section 22 ("app
    fails fast with a clear error if a required variable is missing, rather than failing
    mysteriously later").
    """

    model_config = SettingsConfigDict(
        env_file=".env.local", env_file_encoding="utf-8", extra="ignore"
    )

    env: str = Field(default="dev", alias="ENV")

    database_url: str = Field(alias="DATABASE_URL")
    redis_url: str = Field(alias="REDIS_URL")
    jwt_secret: str = Field(alias="JWT_SECRET")
    object_storage_bucket: str = Field(alias="OBJECT_STORAGE_BUCKET")
    object_storage_endpoint: str = Field(default="", alias="OBJECT_STORAGE_ENDPOINT")
    # Defaults match the docker-compose MinIO service for local dev. Real deployments
    # override these via env vars — never commit real credentials (architecture doc
    # Section 23: secrets exclusively via env vars).
    object_storage_access_key: str = Field(default="minioadmin", alias="OBJECT_STORAGE_ACCESS_KEY")
    object_storage_secret_key: str = Field(default="minioadmin", alias="OBJECT_STORAGE_SECRET_KEY")
    object_storage_region: str = Field(default="us-east-1", alias="OBJECT_STORAGE_REGION")

    llm_provider: str = Field(default="mock", alias="LLM_PROVIDER")
    llm_api_key: str = Field(default="", alias="LLM_API_KEY")
    ocr_provider: str = Field(default="mock", alias="OCR_PROVIDER")
    ocr_api_key: str = Field(default="", alias="OCR_API_KEY")

    # Below this, a document's extraction is never silently accepted as certain — it's
    # flagged needs_manual_review instead (architecture doc "Do Not Do This" rules).
    extraction_confidence_threshold: float = Field(
        default=0.7, alias="EXTRACTION_CONFIDENCE_THRESHOLD"
    )

    access_token_expire_minutes: int = Field(default=15, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_days: int = Field(default=7, alias="REFRESH_TOKEN_EXPIRE_DAYS")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]

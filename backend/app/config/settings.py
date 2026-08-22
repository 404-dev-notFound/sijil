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
    # claude-opus-5 by default — never silently downgraded for cost; change this
    # explicitly if you want a cheaper model for production classification volume.
    llm_model: str = Field(default="claude-opus-5", alias="LLM_MODEL")
    ocr_provider: str = Field(default="mock", alias="OCR_PROVIDER")
    ocr_api_key: str = Field(default="", alias="OCR_API_KEY")

    # Below this, a document's extraction is never silently accepted as certain — it's
    # flagged needs_manual_review instead (architecture doc "Do Not Do This" rules).
    extraction_confidence_threshold: float = Field(
        default=0.7, alias="EXTRACTION_CONFIDENCE_THRESHOLD"
    )

    # Local, no-API-key embedding model (app/integrations/embedding_client.py) — swap
    # only together with TariffHeading.EMBEDDING_DIMENSIONS and a full re-embed.
    embedding_model: str = Field(default="all-MiniLM-L6-v2", alias="EMBEDDING_MODEL")

    # Same "never silently accept a low-confidence guess" rule as extraction, applied
    # to HS classification (architecture doc Section 6.1).
    classification_confidence_threshold: float = Field(
        default=0.7, alias="CLASSIFICATION_CONFIDENCE_THRESHOLD"
    )
    # How many nearest tariff headings to hand the LLM as classification candidates.
    tariff_kb_search_limit: int = Field(default=10, alias="TARIFF_KB_SEARCH_LIMIT")

    access_token_expire_minutes: int = Field(default=15, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_days: int = Field(default=7, alias="REFRESH_TOKEN_EXPIRE_DAYS")

    # Sijil never collects card details directly (architecture doc Section 15) — the
    # billing provider hosts checkout and is the source of truth for subscription
    # state via webhooks. Mock until a real provider (Stripe or a regional
    # equivalent) is configured; set a real, secret value before ever using
    # billing_provider=stripe (or similar) in production.
    billing_provider: str = Field(default="mock", alias="BILLING_PROVIDER")
    billing_webhook_secret: str = Field(
        default="mock-webhook-secret-change-in-production", alias="BILLING_WEBHOOK_SECRET"
    )

    # Short-lived signed download URL TTL for generated reports (API SPEC Section 12:
    # "regenerated on each request rather than permanently public").
    report_download_url_expire_seconds: int = Field(
        default=900, alias="REPORT_DOWNLOAD_URL_EXPIRE_SECONDS"
    )

    # API SPEC Section 15 — brute-force mitigation on auth endpoints. The
    # document-upload limit is explicitly left an open assumption in the plan
    # ("tunable per plan tier... to be tuned against real LLM API costs") and isn't
    # implemented yet — plan tiers don't exist as an enforceable concept until real
    # billing usage data exists to tune against.
    auth_rate_limit_per_minute: int = Field(default=10, alias="AUTH_RATE_LIMIT_PER_MINUTE")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]

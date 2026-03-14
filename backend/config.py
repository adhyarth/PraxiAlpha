"""
PraxiAlpha — Configuration Management

Loads settings from environment variables / .env file.
Uses pydantic-settings for validation and type coercion.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- App ----
    app_env: str = "development"
    app_debug: bool = True
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    secret_key: str = "change-me-in-production"
    log_level: str = "INFO"

    # ---- Database ----
    postgres_user: str = "praxialpha"
    postgres_password: str = "praxialpha_dev_2025"
    postgres_db: str = "praxialpha"
    postgres_host: str = "db"
    postgres_port: int = 5432
    database_url: str = ""

    # ---- Redis ----
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_url: str = ""

    # ---- Celery ----
    celery_broker_url: str = ""
    celery_result_backend: str = ""

    # ---- Data Providers ----
    eodhd_api_key: str = ""
    fred_api_key: str = ""
    te_api_key: str = ""  # TradingEconomics API key (optional, falls back to guest:guest)

    @property
    def async_database_url(self) -> str:
        """Build async database URL if not explicitly set."""
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def sync_database_url(self) -> str:
        """Build sync database URL (for Alembic migrations)."""
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def effective_redis_url(self) -> str:
        if self.redis_url:
            return self.redis_url
        return f"redis://{self.redis_host}:{self.redis_port}/0"

    @property
    def effective_celery_broker_url(self) -> str:
        if self.celery_broker_url:
            return self.celery_broker_url
        return f"redis://{self.redis_host}:{self.redis_port}/0"

    @property
    def effective_celery_result_backend(self) -> str:
        if self.celery_result_backend:
            return self.celery_result_backend
        return f"redis://{self.redis_host}:{self.redis_port}/1"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()

"""Configuration for the domestic electrical data pipeline."""

from typing import Literal
from urllib.parse import quote, urlparse, urlunparse

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Pipeline settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql+asyncpg://mtp:mtp@postgres:5432/mtp"
    app_role_name: str = "mtp_app"
    app_role_password: str = "mtp_app"

    # Runtime environment
    environment: str = "development"

    # Qdrant
    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection_name: str = "cost_items"
    qdrant_knowledge_collection_name: str = "quoting_knowledge"

    # Embeddings (mirrors OCERP configuration)
    embedding_model: str = "text-embedding-3-small"
    openai_api_key: str = ""
    embedding_dimensions: int | None = None

    # Scraping
    apify_api_token: str = ""
    pipeline_demo_mode: bool = False
    screwfix_start_url: str = "https://www.screwfix.com/c/electrical-lighting/cat840780"
    screwfix_max_items: int = 10_000
    screwfix_scrape_details: bool = False
    screwfix_max_total_charge_usd: float = 50.0
    screwfix_timeout_seconds: int = 600
    toolstation_enabled: bool = False

    # Scheduling
    scrape_frequency: Literal["daily", "monthly"] = "monthly"
    monthly_run_day: int = 1
    daily_run_time: str = "02:00"

    @field_validator("database_url")
    @classmethod
    def _ensure_asyncpg_scheme(cls, value: str) -> str:
        """Rewrite plain ``postgresql://`` URLs to the async driver scheme.

        Managed Postgres providers (e.g. Railway) inject ``DATABASE_URL`` as
        ``postgresql://...``, but SQLAlchemy async sessions need
        ``postgresql+asyncpg://``. URLs that already name a driver are left
        untouched.
        """
        if value.startswith("postgresql://"):
            return "postgresql+asyncpg://" + value[len("postgresql://") :]
        if value.startswith("postgres://"):
            return "postgresql+asyncpg://" + value[len("postgres://") :]
        return value

    def get_app_database_url(self) -> str:
        """Return ``database_url`` rewritten to authenticate as ``app_role_name``."""
        parsed = urlparse(self.database_url)
        host = parsed.hostname or "localhost"
        port = f":{parsed.port}" if parsed.port else ""
        password = quote(self.app_role_password, safe="")
        new_netloc = f"{self.app_role_name}:{password}@{host}{port}"
        return urlunparse(parsed._replace(netloc=new_netloc))


settings = Settings()

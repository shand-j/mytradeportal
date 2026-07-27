"""Shared configuration helpers."""

from functools import lru_cache
from urllib.parse import urlparse, urlunparse

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Sentinel values that MUST NOT be used in production. ``validate_production``
# refuses to start the app if any of these are detected when
# ``environment == "production"``.
_INSECURE_DEFAULTS: dict[str, set[str]] = {
    "auth_secret_key": {"dev-auth-secret-key-change-in-production", ""},
    "minio_access_key": {"minioadmin"},
    "minio_secret_key": {"minioadmin"},
}


class InsecureProductionConfigError(RuntimeError):
    """Raised when production settings still contain dev defaults."""


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = Field(default="development")
    database_url: str = Field(default="postgresql+asyncpg://mtp:mtp@localhost:5432/mtp")
    redis_url: str = Field(default="redis://localhost:6379/0")
    qdrant_url: str = Field(default="http://localhost:6333")
    minio_endpoint: str = Field(default="localhost:9000")
    minio_use_ssl: bool = Field(default=False)
    minio_access_key: str = Field(default="minioadmin")
    minio_secret_key: str = Field(default="minioadmin")
    minio_bucket: str = Field(default="mtp-uploads")
    log_level: str = Field(default="INFO")

    # Database role used by the application at runtime. This role must be a
    # regular non-superuser without BYPASSRLS so that PostgreSQL Row-Level
    # Security policies are enforced. The password must be changed from the
    # local-dev default before deploying to production.
    app_role_name: str = Field(default="mtp_app")
    app_role_password: str = Field(default="mtp_app")

    # Payments (Paddle merchant of record)
    paddle_api_key: str = Field(default="")
    paddle_webhook_secret: str = Field(default="")
    paddle_sandbox: bool = Field(default=True)
    paddle_default_currency_code: str = Field(default="GBP")

    # AI / RAG Quote Engine
    openai_api_key: str = Field(default="")
    embedding_model: str = Field(default="text-embedding-3-small")
    embedding_dimensions: int | None = Field(default=None)
    llm_model: str = Field(default="gpt-4o-mini")
    llm_timeout_seconds: int = Field(default=60)
    qdrant_collection_name: str = Field(default="cost_items")
    qdrant_knowledge_collection_name: str = Field(default="quoting_knowledge")
    rag_top_k: int = Field(default=10)
    retrieval_quality_min_citations: int = Field(default=0)
    retrieval_quality_min_top_relevance: float = Field(default=0.0)
    retrieval_quality_require_knowledge_available: bool = Field(default=False)
    retrieval_quality_fallback_policy: str = Field(default="warn_only")
    retrieval_quality_confidence_cap: float = Field(default=0.6)

    # OpenConstructionERP microservice
    ocerp_url: str = Field(default="http://ocerp:8000")

    # Address lookup providers
    fetchify_api_key: str = Field(default="")
    ideal_postcodes_api_key: str = Field(default="")
    # Legacy field retained temporarily for migration fallback.
    getaddress_io_api_key: str = Field(default="")

    # Email / SMTP
    smtp_host: str = Field(default="localhost")
    smtp_port: int = Field(default=1025)
    smtp_use_tls: bool = Field(default=False)
    smtp_username: str = Field(default="")
    smtp_password: str = Field(default="")
    smtp_from_email: str = Field(default="quotes@mytradeportal.local")
    smtp_from_name: str = Field(default="My Trade Portal")

    # Auth
    auth_secret_key: str = Field(default="dev-auth-secret-key-change-in-production")
    auth_access_token_expire_minutes: int = Field(default=60 * 24 * 7)  # 1 week
    auth_cookie_secure: bool = Field(default=True)

    # Tenancy
    default_tenant_slug: str = Field(default="demo")
    allowed_origins: str = Field(default="http://localhost:3000,http://demo.localhost:3000")

    # Supabase Auth (optional — when set, email/password login is handled by Supabase)
    supabase_url: str = Field(default="")
    supabase_anon_key: str = Field(default="")
    supabase_service_role_key: str = Field(default="")

    # Setup / bootstrap token required to create the first tenant in production.
    setup_token: str = Field(default="")

    # Railway feature flags (Signals). Project-scoped token + project id used
    # to read the flag registry from Railway's public GraphQL API at runtime.
    # Empty in local dev — flags then resolve to their (off) defaults.
    railway_token: str = Field(default="")
    railway_project_id: str = Field(default="")

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
        """Return ``database_url`` rewritten to authenticate as ``app_role_name``.

        ``database_url`` is expected to be the Railway-managed superuser URL
        (or any owner URL). The application should connect through the
        lower-privileged app role so Row-Level Security policies are enforced.
        """
        parsed = urlparse(self.database_url)
        host = parsed.hostname or "localhost"
        port = f":{parsed.port}" if parsed.port else ""
        # URL-encode the password so special characters do not break the DSN.
        from urllib.parse import quote

        password = quote(self.app_role_password, safe="")
        new_netloc = f"{self.app_role_name}:{password}@{host}{port}"
        return urlunparse(parsed._replace(netloc=new_netloc))

    def validate_production(self) -> None:
        """Fail fast if production is configured with insecure dev defaults.

        Called from the API lifespan startup so misconfigured production
        deployments refuse to boot instead of silently exposing the dev secret.
        """
        if self.environment != "production":
            return

        violations: list[str] = []
        for field_name, bad_values in _INSECURE_DEFAULTS.items():
            value = getattr(self, field_name, "")
            if value in bad_values:
                violations.append(field_name)

        # The app role must not use the local-dev default password in production.
        if self.app_role_password in {"mtp_app", ""}:
            violations.append("app_role_password")

        # CORS must not be wide open in production.
        if "*" in self.allowed_origins:
            violations.append("allowed_origins (wildcard)")

        if violations:
            raise InsecureProductionConfigError(
                "Refusing to start in production with insecure defaults: "
                + ", ".join(violations)
                + ". Set these via environment variables before deploying."
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()

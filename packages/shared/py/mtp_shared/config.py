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
    # Client-side token (test_.../live_...) used by Paddle.js on the hosted
    # checkout page the mobile app opens. Public by design.
    paddle_client_token: str = Field(default="")
    paddle_sandbox: bool = Field(default=True)
    paddle_default_currency_code: str = Field(default="GBP")
    # Paddle Billing price IDs for the three MTP plans (created in the Paddle
    # dashboard or via Paddle MCP). Empty in dev until wired up.
    paddle_price_id_starter: str = Field(default="")
    paddle_price_id_pro: str = Field(default="")
    paddle_price_id_business: str = Field(default="")
    # When set, every new /billing/checkout transaction auto-applies this
    # discount id. Used during beta to make plans effectively free.
    paddle_beta_discount_id: str = Field(default="")

    # AI / RAG Quote Engine
    openai_api_key: str = Field(default="")
    embedding_model: str = Field(default="text-embedding-3-large")
    embedding_dimensions: int | None = Field(default=None)
    llm_model: str = Field(default="gpt-4o-mini")
    # Optional vision-capable model override for the photo-observation step
    # that captions customer photos attached to quote requests. Empty falls
    # back to ``llm_model`` — set this when the configured chat model cannot
    # accept image input. Routed through the same LiteLLM provider settings
    # (``llm_api_base`` / ``llm_api_key``) as quote generation.
    llm_vision_model: str = Field(default="")
    # Model for the public landing-page demo quote endpoints. The demo favours
    # speed and reliability over flagship quality, so it routes to OpenAI
    # (gpt-4o-mini by default) whenever ``openai_api_key`` is set, ignoring the
    # production ``LLM_MODEL``/``LLM_API_BASE`` (e.g. slow Kimi k2.6). Override
    # per environment via ``DEMO_LLM_MODEL``.
    demo_llm_model: str = Field(default="gpt-4o-mini")
    # Kimi (openai/kimi-k*) quote-generation JSON reliably takes 60-120s, so
    # the default is deliberately above LiteLLM's 60s. Docker overrides via
    # ``LLM_TIMEOUT_SECONDS`` env; keeping the same default here so native /
    # local runs don't spuriously time out.
    llm_timeout_seconds: int = Field(default=180)

    # LLM provider (OpenAI-compatible endpoints). To use Kimi / Moonshot set:
    #   LLM_API_BASE=https://api.moonshot.ai/v1
    #   LLM_API_KEY=<moonshot key>
    #   LLM_MODEL=openai/kimi-k2.6   (the openai/ prefix routes via the
    #                                 OpenAI-compatible handler in LiteLLM)
    #   LLM_TEMPERATURE=             (leave blank: kimi-k* reject a custom
    #                                 temperature; only moonshot-v1 allows it)
    # Empty base/key fall back to the OpenAI defaults + ``openai_api_key``.
    llm_api_base: str = Field(default="")
    llm_api_key: str = Field(default="")
    llm_temperature: float | None = Field(default=0.2)
    # Kimi/Moonshot has intermittent InternalServerError / connection-drop
    # bursts. LiteLLM's ``num_retries`` uses tenacity-style exponential
    # backoff; 3 keeps p99 latency reasonable while covering typical blips.
    llm_max_retries: int = Field(default=3)

    # Cap follow-up chat generation to bound runaway responses. Must stay
    # generous: kimi-k2.6 spends reasoning tokens before content, and a tight
    # cap truncates the completion to empty content (finish_reason=length),
    # which surfaces as the generic fallback question on repeat.
    llm_followup_max_tokens: int = Field(default=8000)

    # Embeddings are provider-specific and Kimi has no embeddings API, so the
    # embedder is configured independently of the chat LLM. It defaults to
    # OpenAI (or any OpenAI-compatible embeddings endpoint). When no embedding
    # key is configured, catalogue retrieval is skipped and quotes are still
    # generated from the model's own guide prices.
    embedding_api_base: str = Field(default="")
    embedding_api_key: str = Field(default="")

    qdrant_collection_name: str = Field(default="cost_items")
    qdrant_knowledge_collection_name: str = Field(default="quoting_knowledge")
    # 5 is a stronger nudge than 10: fewer, higher-quality matches raise the
    # LLM's compliance with catalogue codes (10 wide matches invites Kimi to
    # ignore them all). Override via ``RAG_TOP_K`` env when tuning.
    rag_top_k: int = Field(default=5)
    # Cosine-similarity floor for vector retrieval. Screwfix items that score
    # below this are treated as not-a-match rather than "the best of a bad
    # bunch". 0.45 filters out semantic siblings (burglar-alarms retrieved for
    # smoke-alarm queries, extension reels for SWA cable) that scored 0.40-0.46
    # under the earlier 0.30 floor. Calibrated for text-embedding-3-large.
    rag_min_relevance: float = Field(default=0.45)
    # Retrieval-quality gates consumed by
    # ``app.rag.retrieval.compute_retrieval_quality`` and applied as a
    # confidence cap in ``app.rag.validation.validate_generated_quote``. The
    # min-citations gate defaults to 1 so a zero-retrieval quote is flagged
    # even though it still generates; the top-relevance gate uses the same
    # calibration as the vector floor. Adjust when the eval reveals better
    # cut-offs; keep gate policies conservative in prod.
    retrieval_quality_min_citations: int = Field(default=1)
    retrieval_quality_min_top_relevance: float = Field(default=0.45)
    retrieval_quality_require_knowledge_available: bool = Field(default=False)
    retrieval_quality_fallback_policy: str = Field(
        default="warn_only", pattern="^(warn_only|deterministic_only)$"
    )
    retrieval_quality_confidence_cap: float = Field(default=0.6)

    # Triage / follow-up chat. `max_followup_turns` caps how many AI questions
    # the customer sees before the chat is forced closed. Each turn = 1 AI
    # message + 1 customer reply. Was hard-coded to 3; 5 lets the AI probe
    # more when the initial answers don't tip confidence over 80%.
    max_followup_turns: int = Field(default=5)
    # Hard asyncio budget for one guest-thread AI follow-up turn. The portal
    # awaits the reply synchronously (ai_reply in the POST response), so this
    # gets a larger budget than the inline intake check (12s) — a slow model
    # must not silently degrade the promised "AI follows up" experience to a
    # one-way thread. Fail-open still applies: on timeout the customer's
    # message is stored and the response carries ai_reply=null.
    guest_followup_timeout_seconds: float = Field(default=90.0, gt=0)

    # OpenConstructionERP microservice
    ocerp_url: str = Field(default="http://ocerp:8000")

    # Address lookup providers
    fetchify_api_key: str = Field(default="")
    ideal_postcodes_api_key: str = Field(default="")
    # Legacy field retained temporarily for migration fallback.
    getaddress_io_api_key: str = Field(default="")

    # Email / SMTP (dev fallback via Mailpit)
    smtp_host: str = Field(default="localhost")
    smtp_port: int = Field(default=1025)
    smtp_use_tls: bool = Field(default=False)
    smtp_username: str = Field(default="")
    smtp_password: str = Field(default="")
    smtp_from_email: str = Field(default="quotes@mytradeportal.local")
    smtp_from_name: str = Field(default="My Trade Portal")

    # Resend (preferred production email transport). When ``resend_api_key``
    # is set the email helper skips SMTP and posts to https://api.resend.com.
    # ``resend_from_email`` overrides ``smtp_from_email`` for Resend sends so
    # dev SMTP + prod Resend can each keep their own verified sender. Branded
    # sends (quotes/invoices, which pass a display name) use
    # ``resend_from_email`` — typically the tenant-facing quotes@ address with
    # the tenant's name and Reply-To. Transactional sends (password resets,
    # account mail) use ``resend_no_reply_email`` with the platform name and
    # no Reply-To; it falls back to ``resend_from_email`` when unset.
    resend_api_key: str = Field(default="")
    resend_from_email: str = Field(default="")
    resend_no_reply_email: str = Field(default="")

    # SMS appointment reminders (Telnyx Messaging API). Plan-included feature:
    # customers and the assigned electrician get a text before each appointment.
    # ``telnyx_api_key`` plus at least one of ``telnyx_from_number`` /
    # ``telnyx_messaging_profile_id`` must be set for SMS to be attempted;
    # otherwise appointment reminders degrade to email/push.
    telnyx_api_key: str = Field(default="")
    telnyx_from_number: str = Field(default="")
    telnyx_messaging_profile_id: str = Field(default="")

    # PostHog product analytics (optional passthrough from ``app.analytics``).
    # Empty ``posthog_api_key`` disables the integration entirely — events are
    # still written to the local ``events`` table.
    posthog_api_key: str = Field(default="")
    posthog_host: str = Field(default="https://eu.i.posthog.com")

    # Public base URL used to build customer/staff email links. Falls back to
    # the API's own origin at runtime when unset.
    app_public_url: str = Field(default="")

    # Auth
    auth_secret_key: str = Field(default="dev-auth-secret-key-change-in-production")
    auth_access_token_expire_minutes: int = Field(default=60 * 24 * 7)  # 1 week
    auth_cookie_secure: bool = Field(default=True)

    # Tenancy
    default_tenant_slug: str = Field(default="demo")
    allowed_origins: str = Field(
        default=(
            "http://localhost:3000,http://demo.localhost:3000,"
            "http://localhost:8090,http://localhost:8091,"
            "http://localhost:8092,http://localhost:8093,"
            "http://localhost:8094,http://localhost:8095"
        )
    )
    # Extra origin regex allowing Expo dev-client tunnels and Expo Go previews
    # that use random subdomains under ``exp.host``/``expo.app``. Anything the
    # ops team needs beyond this can still be pushed via the env var.
    allowed_origin_regex: str = Field(
        default=r"^https?://[a-zA-Z0-9-]+\.(exp\.host|expo\.app|expo\.dev)$"
    )

    # Rate limiting. Enabled by default; disabled in the E2E stack so a suite's
    # own repeated logins don't trip the per-IP auth limit.
    rate_limit_enabled: bool = Field(default=True)

    # Langfuse LLM observability (optional). When ``langfuse_public_key`` is
    # set, ``app.ai_telemetry`` mirrors each tracked AI call to Langfuse with
    # the prompt text (prompt text never lands in Postgres). Empty in dev —
    # emission is a no-op. ``langfuse_host`` defaults to the Langfuse cloud
    # when blank; set it for self-hosted installs.
    langfuse_public_key: str = Field(default="")
    langfuse_secret_key: str = Field(default="")
    langfuse_host: str = Field(default="")

    # USD→GBP conversion for AI cost attribution. Used only when the
    # ``fx_rates`` table has no row yet (the weekly refresh job is responsible
    # for keeping it populated); never for customer billing.
    fx_usd_gbp_fallback_rate: float = Field(default=0.79)

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

    @field_validator("llm_temperature", mode="before")
    @classmethod
    def _blank_temperature_to_none(cls, value: object) -> object:
        """Treat a blank ``LLM_TEMPERATURE`` as unset.

        Kimi's ``kimi-k*`` models reject a custom ``temperature`` (it is fixed
        server-side); leaving the env var empty omits the parameter entirely so
        the same code path works for OpenAI, ``moonshot-v1`` and ``kimi-k*``.
        """
        if value is None:
            return None
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    @property
    def resolved_llm_api_key(self) -> str:
        """Chat LLM key, falling back to ``openai_api_key`` for back-compat."""
        return self.llm_api_key or self.openai_api_key

    @property
    def resolved_embedding_api_key(self) -> str:
        """Embeddings key, falling back to ``openai_api_key``."""
        return self.embedding_api_key or self.openai_api_key

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

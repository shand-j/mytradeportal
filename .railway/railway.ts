/**
 * Railway Infrastructure as Code for My Trade Portal V2.
 *
 * Usage (from the repository root, after `railway login` + `railway link`):
 *
 *   railway config plan    # preview the diff against the linked environment
 *   railway config apply   # apply after confirmation
 *
 * Layout (9 resources) — mobile-only beta stack:
 *   postgres + redis      — native Railway database plugins
 *   qdrant, minio         — Docker-image services with mounted volumes
 *   api, admin, data-pipeline — built from this GitHub repo
 *   landing               — Vite marketing site (www.mytradeportal.co.uk),
 *                             built from this GitHub repo via Railpack
 *
 * Not deployed for the mobile beta (parked as commented blocks):
 *   ocerp — BoQ engine, superseded by the LLM quote pipeline
 *   web   — Vite SPA back-office, superseded by the mobile app + Django admin
 *
 * Things this file CANNOT do (Railway IaC beta limitations):
 *   - Generate public service domains. After the first apply, generate domains
 *     in the dashboard for: api, admin. (MinIO is deliberately private-only;
 *     devices never talk to it — file traffic is proxied through the API.)
 *     Until then the `*_RAILWAY_PUBLIC_DOMAIN` references below stay empty.
 *   - Register custom domains (dashboard only, then `railway config pull`).
 *
 * Secrets use preserve(): they are set once in the dashboard and are never
 * overwritten by applies.
 */

import {
  defineRailway,
  github,
  image,
  postgres,
  preserve,
  project,
  redis,
  service,
  volume,
} from "railway/iac";

// GitHub repo deployed via the Railway GitHub App.
const GITHUB_REPO = process.env.MTP_GITHUB_REPO ?? "shand-j/mytradeportal";

const QDRANT_URL = "http://${{qdrant.RAILWAY_PRIVATE_DOMAIN}}:6333";
// MinIO is private-network-only. The private DNS name carries no implied
// port, and MinIO serves the S3 API on 9000 — the port is mandatory here or
// boto3 dials 80 and uploads 503.
const MINIO_ENDPOINT = "${{minio.RAILWAY_PRIVATE_DOMAIN}}:9000";
// OCERP / BoQ engine is parked for the mobile-pivot MVP.
// const OCERP_URL = "http://${{ocerp.RAILWAY_PRIVATE_DOMAIN}}:8000";
const ADMIN_PUBLIC_URL = "https://${{admin.RAILWAY_PUBLIC_DOMAIN}}";
// Hardcoded rather than ${{landing.RAILWAY_PUBLIC_DOMAIN}}: that reference
// resolves to the service's *custom* domain once one is attached, not the
// generated *.up.railway.app origin the beta is viewed on until DNS lands.
const LANDING_PUBLIC_URL = "https://landing-production-e043.up.railway.app";

const TARGET_REGION = "europe-west4-drams3a"; // EU West Metal (Amsterdam) — closest Railway region to the UK market.

export default defineRailway(() => {
  // ---------------------------------------------------------------------
  // Databases (native plugins)
  // ---------------------------------------------------------------------
  const db = postgres("db", { region: TARGET_REGION });
  const cache = redis("redis", { region: TARGET_REGION });

  // ---------------------------------------------------------------------
  // Infrastructure services (Docker images + volumes)
  // ---------------------------------------------------------------------
  const qdrantStorage = volume("qdrant-storage", { sizeMB: 5000, region: TARGET_REGION });
  const minioData = volume("minio-data", { sizeMB: 5000, region: TARGET_REGION });

  const qdrant = service("qdrant", {
    source: image("qdrant/qdrant:v1.11.5"),
    healthcheck: "/healthz",
    volumeMounts: { "/qdrant/storage": qdrantStorage },
    regions: { [TARGET_REGION]: 1 },
    env: {
      // Qdrant listens on 6333; Railway uses $PORT to target healthchecks.
      PORT: "6333",
    },
  });

  const minio = service("minio", {
    // MinIO stopped publishing free images to Docker Hub in late 2025. Use
    // the Quay.io mirror instead. The volume is mounted at /mnt/data to stay
    // clear of the image's VOLUME /data directive, and the start command must
    // invoke the `minio` binary explicitly — Railway replaces the image
    // entrypoint with this command.
    source: image("quay.io/minio/minio:RELEASE.2025-07-23T15-54-02Z"),
    start: 'minio server /mnt/data --console-address ":9001"',
    healthcheck: "/minio/health/live",
    volumeMounts: { "/mnt/data": minioData },
    regions: { [TARGET_REGION]: 1 },
    env: {
      // MinIO root credentials are required. Set them as environment-level
      // variables in Railway, but IaC must reference them with preserve() so
      // they are not deleted on apply/teardown.
      MINIO_ROOT_USER: preserve(),
      MINIO_ROOT_PASSWORD: preserve(),
      // MinIO API listens on 9000; Railway uses $PORT to target healthchecks.
      PORT: "9000",
    },
  });

  // ---------------------------------------------------------------------
  // Application services (built from this repo via the GitHub App)
  // ---------------------------------------------------------------------
  // OCERP / BoQ engine is parked for the mobile-pivot MVP.
  // const ocerp = service("ocerp", {
  //   source: github(GITHUB_REPO),
  //   build: { builder: "DOCKERFILE", dockerfilePath: "services/ocerp/Dockerfile" },
  //   healthcheck: "/health",
  //   regions: { [TARGET_REGION]: 1 },
  //   env: {
  //     ENVIRONMENT: "production",
  //     PORT: "8000",
  //     DATABASE_URL: db.env.DATABASE_URL,
  //     QDRANT_URL,
  //     QDRANT_COLLECTION_NAME: "cost_items",
  //     QDRANT_KNOWLEDGE_COLLECTION_NAME: "quoting_knowledge",
  //     OPENAI_API_KEY: preserve(),
  //     EMBEDDING_MODEL: "text-embedding-3-small",
  //     LLM_MODEL: "gpt-4o-mini",
  //     LLM_TIMEOUT_SECONDS: "300",
  //     LOG_LEVEL: "INFO",
  //     APP_ROLE_NAME: "mtp_app",
  //     APP_ROLE_PASSWORD: preserve(),
  //   },
  // });

  const api = service("api", {
    source: github(GITHUB_REPO),
    build: {
      builder: "DOCKERFILE",
      dockerfilePath: "services/api/Dockerfile",
      watchPatterns: ["services/api/**", "packages/shared/py/**", "scripts/**", "pyproject.toml"],
    },
    healthcheck: "/health",
    preDeployCommand: "python scripts/init_api.py",
    regions: { [TARGET_REGION]: 1 },
    env: {
      ENVIRONMENT: "production",
      LOG_LEVEL: "INFO",
      // No public domain yet → pin PORT so the healthcheck targets the port
      // uvicorn actually listens on (Dockerfile uses ${PORT:-8000}).
      PORT: "8000",
      DATABASE_URL: db.env.DATABASE_URL,
      REDIS_URL: cache.env.REDIS_URL,
      QDRANT_URL,
      QDRANT_COLLECTION_NAME: "cost_items",
      QDRANT_KNOWLEDGE_COLLECTION_NAME: "quoting_knowledge",
      // OCERP_URL,
      // MinIO is private-network-only (no public domain — avoids egress fees
      // and public exposure). All file traffic from devices is proxied through
      // the API (POST /files/upload, GET /files/download), which reaches MinIO
      // over the private network. Never hand MinIO URLs to clients.
      MINIO_ENDPOINT,
      MINIO_USE_SSL: "false",
      MINIO_BUCKET: "mtp-uploads",
      // These secrets are required for production startup. They are set as
      // environment-level variables in Railway, but IaC must reference them with
      // preserve() so they are not deleted on apply/teardown.
      MINIO_ACCESS_KEY: preserve(),
      MINIO_SECRET_KEY: preserve(),
      OPENAI_API_KEY: preserve(),
      // Embedding config must match the data-pipeline service exactly — both
      // read/write the same Qdrant collections. Dimensions are pinned
      // explicitly so an EMBEDDING_MODEL bump can never silently drift from
      // the indexed vector size (3-small=1536 vs 3-large=3072); a mismatch
      // now fails loudly instead of wiping the index.
      EMBEDDING_MODEL: "text-embedding-3-large",
      EMBEDDING_DIMENSIONS: "3072",
      // LiteLLM provider override. Set LLM_API_BASE + LLM_API_KEY to a Kimi /
      // Moonshot key and LLM_MODEL to "openai/kimi-k2.6" for the cheaper,
      // more reliable UK quote model. Leave blank to fall back to OpenAI.
      LLM_MODEL: "openai/kimi-k2.6",
      LLM_API_BASE: preserve(),
      LLM_API_KEY: preserve(),
      // Vision model for the photo-captioning step (AI quote image evidence,
      // #198). Empty = fall back to LLM_MODEL; must be a vision-capable model
      // or photo captioning silently skips (fail-open by design).
      LLM_VISION_MODEL: preserve(),
      LLM_TEMPERATURE: "",
      LLM_MAX_RETRIES: "3",
      LLM_TIMEOUT_SECONDS: "300",
      // Email delivery. Resend is preferred; SMTP is only used if
      // RESEND_API_KEY is unset (there is no SMTP host in prod).
      RESEND_API_KEY: preserve(),
      RESEND_FROM_EMAIL: preserve(),
      // Transactional sender (password resets etc.): platform-branded no-reply.
      RESEND_NO_REPLY_EMAIL: preserve(),
      // Svix signing secret for the Resend bounce webhook (/webhooks/resend).
      RESEND_WEBHOOK_SECRET: preserve(),
      // SMS appointment reminders (Telnyx Messaging API). Plan-included
      // feature; the reminder sweep texts customers + the assigned
      // electrician before each visit (email/push fallback when unset).
      // API key plus one sender identity (from-number or messaging profile).
      TELNYX_API_KEY: preserve(),
      TELNYX_FROM_NUMBER: preserve(),
      TELNYX_MESSAGING_PROFILE_ID: preserve(),
      // Password for the mtp_metabase BI role — init_db keeps the prod role
      // in sync with this on every deploy.
      METABASE_DB_PASSWORD: preserve(),
      // Supabase Auth (staff identity). New-style keys: sb_publishable_ →
      // ANON, sb_secret_ → SERVICE_ROLE. Blank URL = local bcrypt auth.
      SUPABASE_URL: preserve(),
      SUPABASE_ANON_KEY: preserve(),
      SUPABASE_SERVICE_ROLE_KEY: preserve(),
      // Back-office (admin) origin only — NOT used for customer-facing
      // links: portal emails use magic links on {slug}.PORTAL_BASE_DOMAIN,
      // Stripe onboarding returns bounce through PUBLIC_DOCS_BASE_URL, and
      // calendar feeds use CALENDAR_FEED_BASE_URL. Remaining use is
      // staff-facing fallback links (invites, set-password).
      APP_PUBLIC_URL: preserve(),
      // Calendar feed (webcal/.ics) links must resolve to THIS service's
      // public origin — APP_PUBLIC_URL points at the back office, where the
      // feed path 404s as HTML and iOS rejects the subscription.
      CALENDAR_FEED_BASE_URL: "https://api-production-65db.up.railway.app",
      // Where password-reset email links point: the landing site's
      // /reset-password page (NOT the back office).
      PASSWORD_RESET_BASE_URL: "https://www.mytradeportal.co.uk",
      // JWT lifetime for staff + customer sessions: 90 days (129600 min).
      AUTH_ACCESS_TOKEN_EXPIRE_MINUTES: "129600",
      // Public browser origins: the Django admin and the marketing landing
      // (which hosts the no-login AI quote demo calling /demo/*). The native
      // app sends no Origin header, so it needs no entry.
      ALLOWED_ORIGINS: `${ADMIN_PUBLIC_URL},${LANDING_PUBLIC_URL},https://www.mytradeportal.co.uk,https://mytradeportal.co.uk`,
      // Keep production strict: exact allowed origins are defined explicitly
      // by ALLOWED_ORIGINS (set per environment).
      ALLOWED_ORIGIN_REGEX: "",
      // Mandatory in production (validate_production refuses dev defaults).
      AUTH_SECRET_KEY: preserve(),
      // Gates POST /tenants, which bootstraps the first tenant + admin user.
      SETUP_TOKEN: preserve(),
      // Lets GET /feature-flags read this project's Railway Signals registry
      // (RAILWAY_PROJECT_ID is injected natively by Railway). Without it all
      // flags serve their default (off).
      RAILWAY_TOKEN: preserve(),
      // Payments are wired in code but out of alpha scope; set when enabling.
      PADDLE_API_KEY: preserve(),
      PADDLE_WEBHOOK_SECRET: preserve(),
      // Client-side token (test_.../live_...) for the hosted Paddle.js
      // checkout page served at /billing/checkout-page. Public by design.
      PADDLE_CLIENT_TOKEN: preserve(),
      PADDLE_SANDBOX: "true",
      // Paddle Billing catalog IDs. Created via the paddle-sandbox MCP; wire
      // once, keep in the dashboard, IaC picks them up via preserve().
      // Legacy beta-era single monthly prices — still live for existing
      // subscribers; used as fallback by the API plan mapping.
      PADDLE_PRICE_ID_STARTER: preserve(),
      PADDLE_PRICE_ID_PRO: preserve(),
      PADDLE_PRICE_ID_BUSINESS: preserve(),
      // W2-B catalog (2026-09): per-interval prices for the new tiers
      // (sole_trader/pro/team, month+year) plus the metered AI-overage
      // reference price/product. Billing code falls back to the legacy vars
      // while these are unset.
      PADDLE_PRICE_ID_SOLE_TRADER_MONTH: preserve(),
      PADDLE_PRICE_ID_SOLE_TRADER_YEAR: preserve(),
      PADDLE_PRICE_ID_PRO_MONTH: preserve(),
      PADDLE_PRICE_ID_PRO_YEAR: preserve(),
      PADDLE_PRICE_ID_TEAM_MONTH: preserve(),
      PADDLE_PRICE_ID_TEAM_YEAR: preserve(),
      PADDLE_PRICE_ID_AI_OVERAGE: preserve(),
      PADDLE_PRODUCT_ID_AI_OVERAGE: preserve(),
      // Auto-applies a 100% recurring discount to every checkout while set;
      // unset to charge full price once the beta closes.
      PADDLE_BETA_DISCOUNT_ID: preserve(),
      // Stripe Connect (ADR-003): customer → tradie invoice card payments via
      // Express destination charges. Paddle stays subscription-only. Blank
      // defaults; set once in the Railway dashboard, preserved across applies.
      STRIPE_SECRET_KEY: preserve(),
      STRIPE_WEBHOOK_SECRET: preserve(),
      STRIPE_CONNECT_CLIENT_ID: preserve(),
      // Tenant portal (ADR-004): customer-facing pages at
      // https://{slug}.mytradeportal.co.uk. Literal product constant, like
      // PASSWORD_RESET_BASE_URL.
      PORTAL_BASE_DOMAIN: "mytradeportal.co.uk",
      // Portal magic-link lifetime, guest-thread TTL, and the intake-triage
      // model/timeout. Set once in the dashboard; preserve() keeps applies
      // from overwriting them. While unset, the code defaults apply
      // (30 days, gpt-4o-mini, 12s, 120 min).
      PORTAL_MAGIC_TTL_DAYS: preserve(),
      INTAKE_TRIAGE_MODEL: preserve(),
      INTAKE_TRIAGE_TIMEOUT_SECONDS: preserve(),
      GUEST_THREAD_TTL_MINUTES: preserve(),
      // New Relic observability (free tier). Set NEW_RELIC_LICENSE_KEY to enable APM.
      NEW_RELIC_LICENSE_KEY: preserve(),
      NEW_RELIC_APP_NAME: "mytradeportal-api",
      // The API connects as a lower-privilege role so RLS policies are enforced.
      APP_ROLE_NAME: "mtp_app",
      APP_ROLE_PASSWORD: preserve(),
    },
  });

  // Marketing landing (www.mytradeportal.co.uk) — Vite SPA with the no-login
  // AI quote demo, Paddle pricing, blog. Railpack detects Vite; the SPA output
  // dir gives client-side-route fallback (/blog/:slug deep links).
  const landing = service("landing", {
    source: github(GITHUB_REPO, { rootDirectory: "web/landing/new design/app" }),
    build: { builder: "RAILPACK", watchPatterns: ["web/landing/new design/**"] },
    healthcheck: "/",
    regions: { [TARGET_REGION]: 1 },
    env: {
      RAILPACK_SPA_OUTPUT_DIR: "dist",
      // Public by design (present in every browser bundle); values live in the
      // dashboard, picked up here via preserve().
      // API origin for browser calls (demo quote endpoints, password reset).
      // Per-environment reference: each environment's landing calls its OWN
      // api — a hardcoded host means PR preview landings call the stale
      // staging api (which wedged and failed every pr-env-verify run).
      VITE_API_URL: "https://${{api.RAILWAY_PUBLIC_DOMAIN}}",
      VITE_PADDLE_ENV: "sandbox",
      VITE_PADDLE_CLIENT_TOKEN: preserve(),
      // Stripe.js key (pk_...) for the tenant portal invoice /pay page.
      // Public by design (browser-side); set in the dashboard.
      VITE_STRIPE_PUBLISHABLE_KEY: preserve(),
      // Legacy price vars kept until the pricing page cutover is fully rolled
      // out; the landing reads the SOLE_TRADER/PRO/TEAM names below.
      VITE_PADDLE_PRICE_STARTER_MONTH: preserve(),
      VITE_PADDLE_PRICE_PRO_MONTH: preserve(),
      VITE_PADDLE_PRICE_BUSINESS_MONTH: preserve(),
      // W2-B tier price IDs read by the landing pricing page
      // (web/landing pricing-tiers.ts).
      VITE_PADDLE_PRICE_SOLE_TRADER_MONTH: preserve(),
      VITE_PADDLE_PRICE_SOLE_TRADER_YEAR: preserve(),
      VITE_PADDLE_PRICE_PRO_MONTH: preserve(),
      VITE_PADDLE_PRICE_PRO_YEAR: preserve(),
      VITE_PADDLE_PRICE_TEAM_MONTH: preserve(),
      VITE_PADDLE_PRICE_TEAM_YEAR: preserve(),
      VITE_TESTFLIGHT_URL: "https://testflight.apple.com/join/bDFK3bPU",
      // The hero demo calls the public demo endpoints on the api service.
      VITE_DEMO_API_URL: "https://${{api.RAILWAY_PUBLIC_DOMAIN}}",
    },
  });

  // Vite SPA back-office — parked for the mobile beta (the Django admin covers
  // support ops for now). Uncomment + rerun `railway config apply` to bring it
  // back. When re-adding, restore the api service's ALLOWED_ORIGINS to include
  // ${{web.RAILWAY_PUBLIC_DOMAIN}}.
  // const web = service("web", {
  //   source: github(GITHUB_REPO, { rootDirectory: "web/app" }),
  //   build: { builder: "DOCKERFILE", dockerfilePath: "Dockerfile" },
  //   healthcheck: "/",
  //   regions: { [TARGET_REGION]: 1 },
  //   env: {
  //     // Route browser API calls through web's /api reverse proxy, which then
  //     // uses Railway private networking to reach the API service.
  //     VITE_API_BASE_URL: "/api",
  //     API_UPSTREAM_URL: "http://${{api.RAILWAY_PRIVATE_DOMAIN}}:8000",
  //     // Match nginx template ${PORT}; Railway overrides $PORT otherwise.
  //     PORT: "80",
  //   },
  // });

  const admin = service("admin", {
    source: github(GITHUB_REPO),
    build: {
      builder: "DOCKERFILE",
      dockerfilePath: "services/admin/Dockerfile",
      watchPatterns: ["services/admin/**", "packages/shared/py/**", "scripts/init_db.py", "scripts/init_api.py"],
    },
    healthcheck: "/health",
    preDeployCommand: "sh -c 'python manage.py migrate --noinput && python scripts/ensure_superuser.py'",
    regions: { [TARGET_REGION]: 1 },
    env: {
      // Django uses psycopg2, so the plugin's plain postgresql:// URL is correct.
      DATABASE_URL: db.env.DATABASE_URL,
      SECRET_KEY: preserve(),
      DEBUG: "False",
      ALLOWED_HOSTS: "${{admin.RAILWAY_PUBLIC_DOMAIN}},${{admin.RAILWAY_PRIVATE_DOMAIN}},localhost,127.0.0.1",
      CSRF_TRUSTED_ORIGINS: ADMIN_PUBLIC_URL,
      // Match Dockerfile EXPOSE and gunicorn bind port; Railway overrides $PORT otherwise.
      PORT: "8001",
      // Deploy with a Django superuser for tenant creation and admin maintenance.
      // Set these values in Railway/GitHub secrets before first deploy.
      DJANGO_SUPERUSER_USERNAME: preserve(),
      DJANGO_SUPERUSER_EMAIL: preserve(),
      DJANGO_SUPERUSER_PASSWORD: preserve(),
      // New Relic observability (free tier). Set NEW_RELIC_LICENSE_KEY to enable APM.
      NEW_RELIC_LICENSE_KEY: preserve(),
      NEW_RELIC_APP_NAME: "mytradeportal-admin",
      APP_ROLE_NAME: "mtp_app",
      APP_ROLE_PASSWORD: preserve(),
    },
  });

  const dataPipeline = service("data-pipeline", {
    source: github(GITHUB_REPO),
    build: {
      builder: "DOCKERFILE",
      dockerfilePath: "services/data-pipeline/Dockerfile",
      watchPatterns: ["services/data-pipeline/**", "packages/shared/py/**"],
    },
    start: "newrelic-admin run-program python -m data_pipeline.scheduler",
    healthcheck: "/health",
    regions: { [TARGET_REGION]: 1 },
    env: {
      DATABASE_URL: db.env.DATABASE_URL,
      QDRANT_URL,
      QDRANT_COLLECTION_NAME: "cost_items",
      QDRANT_KNOWLEDGE_COLLECTION_NAME: "quoting_knowledge",
      OPENAI_API_KEY: preserve(),
      // Must match the api service's embedding model AND dimensions — both
      // read/write the same Qdrant collections, and 3-small (1536 dims) vs
      // 3-large (3072 dims) would silently break retrieval. Keep
      // EMBEDDING_DIMENSIONS pinned in both services.
      EMBEDDING_MODEL: "text-embedding-3-large",
      EMBEDDING_DIMENSIONS: "3072",
      APIFY_API_TOKEN: preserve(),
      PIPELINE_DEMO_MODE: "false",
      SCREWFIX_START_URL: "https://www.screwfix.com/c/electrical-lighting/cat840780",
      SCREWFIX_MAX_ITEMS: "10000",
      SCREWFIX_SCRAPE_DETAILS: "false",
      SCREWFIX_MAX_TOTAL_CHARGE_USD: "50",
      SCREWFIX_TIMEOUT_SECONDS: "600",
      TOOLSTATION_ENABLED: "false",
      SCRAPE_FREQUENCY: "monthly",
      PORT: "8000",
      // New Relic observability. Set NEW_RELIC_LICENSE_KEY to enable APM; the
      // start command above wraps the scheduler with newrelic-admin (the IaC
      // start overrides the Dockerfile CMD, so the wrapper lives here).
      NEW_RELIC_LICENSE_KEY: preserve(),
      NEW_RELIC_APP_NAME: "mytradeportal-data-pipeline",
      APP_ROLE_NAME: "mtp_app",
      APP_ROLE_PASSWORD: preserve(),
    },
  });

  return project("mytradeportal", {
    resources: [db, cache, qdrant, minio, api, admin, dataPipeline, landing, qdrantStorage, minioData],
  });
});

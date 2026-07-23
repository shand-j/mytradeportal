/**
 * Railway Infrastructure as Code for My Trade Portal V2.
 *
 * Usage (from the repository root, after `railway login` + `railway link`):
 *
 *   railway config plan    # preview the diff against the linked environment
 *   railway config apply   # apply after confirmation
 *
 * Layout (9 resources):
 *   postgres + redis      — native Railway database plugins
 *   qdrant, minio         — Docker-image services with mounted volumes
 *   api, ocerp, web, admin, data-pipeline — built from this GitHub repo
 *
 * Things this file CANNOT do (Railway IaC beta limitations):
 *   - Generate public service domains. After the first apply, generate domains
 *     in the dashboard for: api, web, admin, minio (target port 9000). Until
 *     then the `*_RAILWAY_PUBLIC_DOMAIN` references below stay empty.
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
const OCERP_URL = "http://${{ocerp.RAILWAY_PRIVATE_DOMAIN}}:8000";
const API_PUBLIC_URL = "https://${{api.RAILWAY_PUBLIC_DOMAIN}}";
const WEB_PUBLIC_URL = "https://${{web.RAILWAY_PUBLIC_DOMAIN}}";
const ADMIN_PUBLIC_URL = "https://${{admin.RAILWAY_PUBLIC_DOMAIN}}";

export default defineRailway(() => {
  // ---------------------------------------------------------------------
  // Databases (native plugins)
  // ---------------------------------------------------------------------
  const db = postgres("db");
  const cache = redis("redis");

  // ---------------------------------------------------------------------
  // Infrastructure services (Docker images + volumes)
  // ---------------------------------------------------------------------
  const qdrant = service("qdrant", {
    source: image("qdrant/qdrant:v1.11.5"),
    volumeMounts: { "/qdrant/storage": volume("qdrant-storage", { sizeMB: 5000, region: "sfo" }) },
  });

  const minio = service("minio", {
    // NOTE: the previously pinned 2024 tag fails to start on Railway (instant
    // FAILED deploy with no logs); latest deploys cleanly. The volume is
    // mounted at /mnt/data to stay clear of the image's VOLUME /data
    // directive, and the start command must invoke the `minio` binary
    // explicitly — Railway replaces the image entrypoint with this command.
    source: image("minio/minio:latest"),
    start: 'minio server /mnt/data --console-address ":9001"',
    volumeMounts: { "/mnt/data": volume("minio-data", { sizeMB: 5000, region: "sfo" }) },
    env: {
      // Set real credentials in the dashboard before first deploy.
      MINIO_ROOT_USER: preserve(),
      MINIO_ROOT_PASSWORD: preserve(),
    },
  });

  // ---------------------------------------------------------------------
  // Application services (built from this repo via the GitHub App)
  // ---------------------------------------------------------------------
  const ocerp = service("ocerp", {
    source: github(GITHUB_REPO),
    build: { builder: "DOCKERFILE", dockerfilePath: "services/ocerp/Dockerfile" },
    healthcheck: "/health",
    env: {
      ENVIRONMENT: "production",
      // No public domain → Railway doesn't inject PORT; pin it so the
      // healthcheck targets the port uvicorn actually listens on.
      PORT: "8000",
      DATABASE_URL: db.env.DATABASE_URL,
      QDRANT_URL,
      QDRANT_COLLECTION_NAME: "cost_items",
      QDRANT_KNOWLEDGE_COLLECTION_NAME: "quoting_knowledge",
      OPENAI_API_KEY: preserve(),
      EMBEDDING_MODEL: "text-embedding-3-small",
      LLM_MODEL: "gpt-4o-mini",
      LLM_TIMEOUT_SECONDS: "300",
      LOG_LEVEL: "INFO",
    },
  });

  const api = service("api", {
    source: github(GITHUB_REPO),
    build: { builder: "DOCKERFILE", dockerfilePath: "services/api/Dockerfile" },
    healthcheck: "/health",
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
      OCERP_URL,
      // Presigned upload URLs are fetched by the browser, so MinIO must be
      // reached via its PUBLIC domain over HTTPS (MINIO_USE_SSL=true).
      MINIO_ENDPOINT: minio.env.RAILWAY_PUBLIC_DOMAIN,
      MINIO_USE_SSL: "true",
      MINIO_ACCESS_KEY: preserve(),
      MINIO_SECRET_KEY: preserve(),
      MINIO_BUCKET: "mtp-uploads",
      OPENAI_API_KEY: preserve(),
      EMBEDDING_MODEL: "text-embedding-3-small",
      LLM_MODEL: "gpt-4o-mini",
      LLM_TIMEOUT_SECONDS: "300",
      ALLOWED_ORIGINS: WEB_PUBLIC_URL,
      // Mandatory in production (validate_production refuses dev defaults):
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
      PADDLE_SANDBOX: "true",
    },
  });

  const web = service("web", {
    source: github(GITHUB_REPO, { rootDirectory: "web/app" }),
    build: { builder: "DOCKERFILE", dockerfilePath: "Dockerfile" },
    healthcheck: "/",
    env: {
      // Baked into the Vite bundle at build time (Docker build ARG).
      VITE_API_BASE_URL: API_PUBLIC_URL,
    },
  });

  const admin = service("admin", {
    source: github(GITHUB_REPO),
    build: { builder: "DOCKERFILE", dockerfilePath: "services/admin/Dockerfile" },
    healthcheck: "/admin/login/",
    env: {
      // Django uses psycopg2, so the plugin's plain postgresql:// URL is correct.
      DATABASE_URL: db.env.DATABASE_URL,
      SECRET_KEY: preserve(),
      DEBUG: "False",
      ALLOWED_HOSTS: "${{admin.RAILWAY_PUBLIC_DOMAIN}}",
      CSRF_TRUSTED_ORIGINS: ADMIN_PUBLIC_URL,
    },
  });

  const dataPipeline = service("data-pipeline", {
    source: github(GITHUB_REPO),
    build: { builder: "DOCKERFILE", dockerfilePath: "services/data-pipeline/Dockerfile" },
    env: {
      DATABASE_URL: db.env.DATABASE_URL,
      QDRANT_URL,
      QDRANT_COLLECTION_NAME: "cost_items",
      QDRANT_KNOWLEDGE_COLLECTION_NAME: "quoting_knowledge",
      OPENAI_API_KEY: preserve(),
      EMBEDDING_MODEL: "text-embedding-3-small",
      APIFY_API_TOKEN: preserve(),
      PIPELINE_DEMO_MODE: "false",
      SCREWFIX_START_URL: "https://www.screwfix.com/c/electrical-lighting/cat840780",
      SCREWFIX_MAX_ITEMS: "10000",
      SCREWFIX_SCRAPE_DETAILS: "false",
      SCREWFIX_MAX_TOTAL_CHARGE_USD: "50",
      SCREWFIX_TIMEOUT_SECONDS: "600",
      TOOLSTATION_ENABLED: "false",
      SCRAPE_FREQUENCY: "monthly",
    },
  });

  return project("mytradeportal", {
    resources: [db, cache, qdrant, minio, api, ocerp, web, admin, dataPipeline],
  });
});

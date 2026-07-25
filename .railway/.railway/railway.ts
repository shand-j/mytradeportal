import { defineRailway, github, image, postgres, preserve, project, redis, service, volume } from "railway/iac";

export default defineRailway(() => {
  const mytradeportal = github("shand-j/mytradeportal", { checkSuites: false });

  const db = postgres("db", { region: "europe-west4-drams3a" });
  const redisDatabase = redis("redis", { region: "europe-west4-drams3a" });
  redisDatabase.deploy = { startCommand: "/bin/sh -c \"rm -rf $RAILWAY_VOLUME_MOUNT_PATH/lost+found/ && exec docker-entrypoint.sh redis-server --requirepass $REDIS_PASSWORD --save 60 1 --dir $RAILWAY_VOLUME_MOUNT_PATH\"" };
  const dbVolumeHguc = volume("db-volume-Hguc", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: "europe-west4-drams3a", sizeMB: 5000 });
  const redisVolumeFUQP = volume("redis-volume-fUQP", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: "europe-west4-drams3a", sizeMB: 5000 });
  const redisVolume3_Qv = volume("redis-volume-3_Qv", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: "sfo", sizeMB: 5000 });
  const minio = service("minio", {
    source: image("quay.io/minio/minio:RELEASE.2025-07-23T15-54-02Z"),
    start: "minio server /mnt/data --console-address \":9001\"",
    healthcheck: "/minio/health/live",
    replicas: { "europe-west4-drams3a": 1 },
    env: {
      PORT: preserve(),
    },
  });
  const admin = service("admin", {
    source: mytradeportal,
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "services/admin/Dockerfile" },
    healthcheck: "/health",
    replicas: { "europe-west4-drams3a": 1 },
    deploy: { preDeployCommand: ["sh -c 'python manage.py migrate --noinput && python scripts/ensure_superuser.py'"] },
    env: {
      ALLOWED_HOSTS: preserve(),
      APP_ROLE_NAME: preserve(),
      APP_ROLE_PASSWORD: preserve(),
      CSRF_TRUSTED_ORIGINS: preserve(),
      DATABASE_URL: preserve(),
      DEBUG: preserve(),
      DJANGOUSER_EMAIL: preserve(),
      DJANGO_SUPERUSER_EMAIL: preserve(),
      DJANGO_SUPERUSER_PASSWORD: preserve(),
      DJANGO_SUPERUSER_USERNAME: preserve(),
      NEW_RELIC_APP_NAME: preserve(),
      NEW_RELIC_LICENSE_KEY: preserve(),
      PORT: preserve(),
      SECRET_KEY: preserve(),
    },
  });
  const dataPipeline = service("data-pipeline", {
    source: mytradeportal,
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "services/data-pipeline/Dockerfile" },
    start: "python -m data_pipeline.scheduler",
    healthcheck: "/health",
    replicas: { "europe-west4-drams3a": 1 },
    deploy: { restartPolicyType: "NEVER" },
    env: {
      APIFY_API_TOKEN: preserve(),
      APP_ROLE_NAME: preserve(),
      APP_ROLE_PASSWORD: preserve(),
      DATABASE_URL: preserve(),
      EMBEDDING_MODEL: preserve(),
      OPENAI_API_KEY: preserve(),
      PIPELINE_DEMO_MODE: preserve(),
      PORT: preserve(),
      QDRANT_COLLECTION_NAME: preserve(),
      QDRANT_KNOWLEDGE_COLLECTION_NAME: preserve(),
      QDRANT_URL: preserve(),
      SCRAPE_FREQUENCY: preserve(),
      SCREWFIX_MAX_ITEMS: preserve(),
      SCREWFIX_MAX_TOTAL_CHARGE_USD: preserve(),
      SCREWFIX_SCRAPE_DETAILS: preserve(),
      SCREWFIX_START_URL: preserve(),
      SCREWFIX_TIMEOUT_SECONDS: preserve(),
      TOOLSTATION_ENABLED: preserve(),
    },
  });
  const qdrant = service("qdrant", {
    source: image("qdrant/qdrant:v1.11.5"),
    healthcheck: "/healthz",
    replicas: { "europe-west4-drams3a": 1 },
    env: {
      PORT: preserve(),
    },
  });
  const api = service("api", {
    source: mytradeportal,
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "services/api/Dockerfile" },
    healthcheck: "/health",
    replicas: { "europe-west4-drams3a": 1 },
    deploy: { preDeployCommand: ["python scripts/init_api.py"] },
    env: {
      ALLOWED_ORIGINS: preserve(),
      APP_ROLE_NAME: preserve(),
      APP_ROLE_PASSWORD: preserve(),
      AUTH_SECRET_KEY: preserve(),
      DATABASE_URL: preserve(),
      EMBEDDING_MODEL: preserve(),
      ENVIRONMENT: preserve(),
      LLM_MODEL: preserve(),
      LLM_TIMEOUT_SECONDS: preserve(),
      LOG_LEVEL: preserve(),
      MINIO_ACCESS_KEY: preserve(),
      MINIO_BUCKET: preserve(),
      MINIO_ENDPOINT: preserve(),
      MINIO_SECRET_KEY: preserve(),
      MINIO_USE_SSL: preserve(),
      NEW_RELIC_APP_NAME: preserve(),
      NEW_RELIC_LICENSE_KEY: preserve(),
      OCERP_URL: preserve(),
      OPENAI_API_KEY: preserve(),
      PADDLE_SANDBOX: preserve(),
      PORT: preserve(),
      QDRANT_COLLECTION_NAME: preserve(),
      QDRANT_KNOWLEDGE_COLLECTION_NAME: preserve(),
      QDRANT_URL: preserve(),
      RAILWAY_TOKEN: preserve(),
      REDIS_URL: preserve(),
      SETUP_TOKEN: preserve(),
    },
  });
  const web = service("web", {
    source: github("shand-j/mytradeportal", { checkSuites: false, rootDirectory: "web/app" }),
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "Dockerfile" },
    healthcheck: "/",
    replicas: { "europe-west4-drams3a": 1 },
    env: {
      PORT: preserve(),
      VITE_API_BASE_URL: preserve(),
    },
  });
  const ocerp = service("ocerp", {
    source: mytradeportal,
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "services/ocerp/Dockerfile" },
    healthcheck: "/health",
    replicas: { "europe-west4-drams3a": 1 },
    env: {
      APP_ROLE_NAME: preserve(),
      APP_ROLE_PASSWORD: preserve(),
      DATABASE_URL: preserve(),
      EMBEDDING_MODEL: preserve(),
      ENVIRONMENT: preserve(),
      LLM_MODEL: preserve(),
      LLM_TIMEOUT_SECONDS: preserve(),
      LOG_LEVEL: preserve(),
      OPENAI_API_KEY: preserve(),
      PORT: preserve(),
      QDRANT_COLLECTION_NAME: preserve(),
      QDRANT_KNOWLEDGE_COLLECTION_NAME: preserve(),
      QDRANT_URL: preserve(),
    },
  });

  return project("MyTradePortal", {
    resources: [minio, admin, db, redisDatabase, dataPipeline, qdrant, api, web, ocerp, dbVolumeHguc, redisVolumeFUQP, redisVolume3_Qv],
  });
});

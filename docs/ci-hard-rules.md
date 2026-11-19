# CI hard rules

These rules exist to keep CI deterministic, free of third-party quota/cost, and
safe to run on every PR. They are enforced in `.github/workflows/ci.yml` and
referenced from the other workflows.

## 1. No live LLM or Paddle calls in CI

CI must never call a live LLM provider or the live Paddle API:

- No workflow sets `LLM_API_KEY`, `OPENAI_API_KEY`, or `PADDLE_API_KEY` —
  do not add them to any workflow, job, or step.
- The AI-quote eval harness (`services/api/evals`) runs **offline** by default,
  replaying canned LLM responses from `fixtures/`; its `--live` mode is a
  local-only tool and must stay out of CI.
- Tests that touch LLM or Paddle code paths use mocks or forged,
  locally-signed webhooks (see `services/api/tests/test_webhooks.py`,
  `test_ai_quality.py`). The staging E2E write suite signs Paddle webhook
  payloads locally with the *sandbox* webhook secret read from the staging
  environment — it never calls the Paddle API.

Rationale: live calls would make CI non-deterministic, burn quota, and leak
credentials into a context that must remain safe for forked-PR style workflows.

## 2. Schema changes are gated by the `schema-sync` job

This project has **no Alembic migrations**. `scripts/init_db.py` is the single
source of truth for the API schema: it creates tables from the current
SQLAlchemy models, reconciles missing columns on existing tables
(`sync_missing_columns`, with a safe two-step backfill for `NOT NULL` columns),
creates the app/BI roles, and applies RLS. A classic "migrations up AND down"
gate therefore does not apply literally.

Instead, the `schema-sync` job in `ci.yml` proves the two properties a
migration gate exists for, on every PR and push:

1. **Idempotency** — `init_db.py` runs twice against a fresh Postgres; the
   second run must reconcile nothing. This is the property that makes the
   script safe as the Railway preDeploy command on every deploy.
2. **Reconcile against an older prod-like schema** — the job drops a recently
   added column (`quotes.rounding_adjustment`) to simulate a production
   database from an older release, then asserts the sync re-adds it. This is
   the "up" direction of the gate.

**Honest limitations:** there is no prod-like dump fixture in the repo, so the
"older schema" is simulated rather than a real `pg_dump` restore, and there is
no "down" direction (schema-sync never removes columns). If a sanitised dump
fixture is ever added (e.g. under `services/api/tests/fixtures/`), extend the
job to restore it and run `init_db.py` against the restored dump before
declaring this fully covered.

## 3. Railway IaC deployment requires manual intervention

The `deploy-production` job in `ci.yml` runs `railway config apply` to sync
infrastructure changes (e.g. service image updates, volume mounts, environment
variables) defined in `.railway/railway.ts`. **This step fails silently when
the CI project token is rejected** by Railway CLI v5.28+.

**What this means:**
- ✅ Code deploys work: Railway's GitHub integration rebuilds services on every
  push to main (verified on 2026-09-16).
- ❌ Infrastructure changes do NOT apply automatically:
  - Service image swaps (MinIO → RustFS, etc.)
  - Volume/environment config updates
  - Region corrections

**When you change `.railway/railway.ts`:**
1. The PR/commit is safe — it only updates the configuration file
2. After merge to main, **manually run** (locally with Railway CLI):
   ```bash
   cd .railway
   railway login
   railway link  # if needed
   railway config apply --confirm-destructive
   ```
3. See `docs/runbooks/deploy-rustfs-iac.md` for a detailed walkthrough

**Why this limitation exists:**
Railway CLI v5.28+ rejects project-scoped tokens (required for CI) but accepts
browser-authenticated sessions. A fix would require either:
- Upgrading the Railway IaC framework to use a new token format
- Switching to the Railway GraphQL API (not currently used in CI)
- Using a human-scoped token (not secure for CI)

This limitation is documented in the CI workflow as a yellow warning (not a
failure) so code deploys are never blocked.

## 4. Feature flags for unfinished user-visible work

Anything user-visible that ships before it is fully baked goes behind a
feature flag (`services/api/app/feature_flags.py`, covered by
`services/api/tests/test_feature_flags.py`). This is a code-review rule rather
than a CI-enforced gate — CI cannot detect "user-visible" — but it is listed
here so the full set of hard rules lives in one place.

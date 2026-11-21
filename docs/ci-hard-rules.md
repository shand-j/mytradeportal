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

  Staging quote generation, refinement and triage follow-up paths use the
  `LLM_PROVIDER_MODE=staging_double` external-provider boundary. The real API
  retrieval, validation, persistence and journey assertions remain in play; only
  chat-completion responses are deterministic doubles. No staging test may treat
  a 503 AI response as a pass or skip the generation/follow-up journey. A live
  provider run remains a separate manual, credentialed check outside CI.

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

## 3. Railway IaC deployment must fail closed

The `deploy-production` job in `ci.yml` and the `apply-staging-iac` job in
`staging-e2e.yml` run `railway config apply` to sync infrastructure changes
(e.g. service image updates, volume mounts, environment variables) defined in
`.railway/railway.ts`. Both jobs treat a CLI error or an explicit Railway token
rejection as a hard failure.

**What this means:**
- ✅ Code deploys work: Railway's GitHub integration rebuilds services on every
  push to main (verified on 2026-09-16).
- ✅ Infrastructure changes apply to production on `main` pushes and to staging
  before the staging smoke suites:
  - Service image swaps (MinIO → RustFS, etc.)
  - Volume/environment config updates
  - Region corrections

**When you change `.railway/railway.ts`:**
1. The PR/commit is safe — it only updates the configuration file
2. CI applies it to production and staging after merge to main
3. If the deploy job reports a rejected token, restore CI by rotating the
   environment's `RAILWAY_TOKEN` to a CLI-compatible account token. As a
   one-off recovery, run locally with a browser-authenticated session:
   ```bash
   cd .railway
   railway login
   railway link  # if needed
   railway config apply --confirm-destructive
   ```
4. See `docs/runbooks/deploy-rustfs-iac.md` for deployment and verification
   details

**Why this limitation exists:**
Railway CLI v5.28+ rejects some older project-scoped token formats but accepts
compatible account tokens and browser-authenticated sessions. Token rejection
must never be tolerated: a green code deployment with stale infrastructure can
leave an environment running an obsolete service image.

## 4. Feature flags for unfinished user-visible work

Anything user-visible that ships before it is fully baked goes behind a
feature flag (`services/api/app/feature_flags.py`, covered by
`services/api/tests/test_feature_flags.py`). This is a code-review rule rather
than a CI-enforced gate — CI cannot detect "user-visible" — but it is listed
here so the full set of hard rules lives in one place.

## 5. Staging verification must be fresh, bounded, and attributable

The `staging-e2e.yml` workflow is a release gate; stale or hung runs are not
acceptable evidence.

- **Queue/cancellation semantics**: push-triggered staging runs use
  ref-scoped concurrency with `cancel-in-progress: true`, so the newest push to
  `main` always wins and older in-flight runs are cancelled.
- **Bounded execution**: each staging job has `timeout-minutes` so a hung
  deployment wait or test job cannot block the queue indefinitely.
- **Actionable stale-run diagnostic**: the workflow fails fast on push runs
  when `GITHUB_SHA` is no longer the branch head, with a direct message to use
  the newest run for fresh evidence.

A cancelled or timed-out staging run is never a pass and must be replaced by a
green run for the latest commit.

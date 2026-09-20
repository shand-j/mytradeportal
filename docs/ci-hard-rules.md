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

## 3. Feature flags for unfinished user-visible work

Anything user-visible that ships before it is fully baked goes behind a
feature flag (`services/api/app/feature_flags.py`, covered by
`services/api/tests/test_feature_flags.py`). This is a code-review rule rather
than a CI-enforced gate — CI cannot detect "user-visible" — but it is listed
here so the full set of hard rules lives in one place.

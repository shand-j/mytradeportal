# PR-environment CI verification

Every PR is verified against its own **Railway PR environment** — an ephemeral
copy of production that Railway's GitHub integration creates automatically
when the PR opens — so `main` can be locked behind passing CI.

Workflow: [`.github/workflows/pr-verify.yml`](../.github/workflows/pr-verify.yml)

## Jobs

1. **quality-gates** — identical setup to the `python` job in `ci.yml`: ruff
   (lint + format), mypy (`services/api`, `packages/shared/py`, `services/admin`),
   and the full in-process pytest suite against postgres/qdrant/redis service
   containers. No network access to LLM or Paddle providers exists in this job;
   tests run purely on fixtures/mocks.
2. **pr-env-verify** (after quality-gates pass):
   1. Resolves the PR environment's public URLs (see below), retrying for up
      to 15 minutes — Railway creates the environment when the PR opens, but
      the copy-of-production deploy takes several minutes.
   2. Polls `GET {api}/health` until it returns 200 (up to 15 minutes).
   3. Runs the deployed-API smoke suite
      ([`services/api/tests_deployed/`](../services/api/tests_deployed)) with
      `TEST_API_BASE_URL` set to the PR environment's API URL.
   4. Runs a light Playwright suite (`web/app/playwright.pr.config.ts`,
      specs in `web/app/e2e/pr-env/`, chromium only) against the PR
      environment's landing URL via `TEST_LANDING_URL`. Unlike the main
      `playwright.config.ts` it starts **no** Docker stack and uses **no**
      auth fixtures.
   5. Posts a comment on the PR with both URLs and the results.

   Concurrency is `cancel-in-progress` per PR, so pushing new commits cancels
   the superseded verification run.

## PR environment discovery

`scripts/ci/pr_env_url.sh <pr-number>` resolves URLs in this order:

1. Explicit overrides: `RAILWAY_PR_API_URL` / `RAILWAY_PR_LANDING_URL`.
2. Railway CLI discovery:
   - `railway environment list --ephemeral --json` — finds the ephemeral
     environment named `pr-<number>` / `pr-<number>-<branch>`;
   - `railway domain list --service api|landing --environment <env> --json` —
     takes the first active service-type domain (custom domains are ignored).

   Requires the Railway CLI authenticated via `RAILWAY_TOKEN` (CI) or an
   interactive login (local). Local sanity check against the linked project:

   ```bash
   ./scripts/ci/pr_env_url.sh 123
   # exits 3 with "no ephemeral PR environment found for PR #123 ..." until
   # the Railway GitHub integration has created one for that PR
   ```

## Required GitHub secrets

| Secret | Purpose |
|---|---|
| `RAILWAY_TOKEN` | Project-scoped Railway token used by the CLI for environment/domain discovery (same token the existing `deploy-production` job uses). |
| `GITHUB_TOKEN` | Built-in; needs `pull-requests: write` for the result comment (granted in the workflow). |

## What the smoke suites do (and deliberately don't)

**Deployed API** (`pytest services/api/tests_deployed`, marker `deployed`,
excluded from the default pytest run): `/health`, `/ready`, auth-token 401,
auth-required gates on `/auth/tenant-status` and `/payments/status`, public
business-config 404/contract, public-docs 404s on bogus tokens, Resend webhook
rejects a bad signature, intake 404 on an unknown slug, OpenAPI docs. All are
non-destructive and need no seeded tenant.

**Landing/portal** (Playwright): home loads with hero/pricing/quote demo,
`/fair-use` renders, `/quote/:token` and `/pay/:token` show the invalid-link
error state for bogus tokens.

### Limitations

- **No live LLM or Paddle calls.** The intake POST is the one write-path test:
  it only runs when `TEST_SETUP_TOKEN` is set (never in CI), creates a
  throwaway UUID-slug tenant, and posts with `sync_check=false`. Note the API
  still schedules its background AI auto-draft for any submitted intake, so
  even that opt-in test triggers one background LLM call against the target
  environment — run it only against ephemeral PR environments.
- **PR environments copy production variables.** Never put real customer data
  or real secrets in test payloads; the environment is as privileged as
  production until the PR closes.
- **The PR environment has its own database** (copy of production at creation
  time). Seeded-tenant-dependent tests are opt-in via `TEST_PUBLIC_SLUG`.
- **Forks**: `pull_request` runs from forks do not receive secrets, so
  `pr-env-verify` fails for external forks. Use `workflow_dispatch` with the
  PR number, or run the suite locally (see below).
- **Ephemeral environment lifetime**: Railway tears the PR environment down
  when the PR closes; re-running the workflow afterwards requires re-opening
  the PR or dispatching manually.

## Running locally

Read-only subset against any deployment:

```bash
source .venv/bin/activate
TEST_API_BASE_URL=https://<api-host> python -m pytest services/api/tests_deployed -o addopts='' -v

cd web/app
TEST_LANDING_URL=https://<landing-host> pnpm exec playwright test --config playwright.pr.config.ts
```

# Engineering orchestrator

Always-on, policy-gated engineering automation using CrewAI Flow, Kimi Code CLI, Railway Sandboxes, and GitHub.

## Local verification

```bash
cd services/engineering_orchestrator
cp .env.example .env
crewai install
uv run pytest
uv run uvicorn engineering_orchestrator.api:create_app --factory --reload --port 8010
```

The default `dry_run` mode persists and triages events without creating sandboxes, branches, PRs, or deployments.

## HTTP surface

- `POST /webhooks/github`: GitHub `issues` webhook; implementation requires the `agent:ready` label and `X-Hub-Signature-256`.
- `POST /webhooks/alerts`: signed production alert webhook. Alerts use `X-Engineering-Timestamp` and a hex HMAC-SHA256 in `X-Engineering-Signature` over `<timestamp>.<raw-body>`.
- `POST /webhooks/testflight`: signed relay endpoint for already-normalized crash/feedback submissions.
- `GET /runs`, `GET /runs/{id}`, `POST /runs/{id}/retry`: require `X-Engineering-Token`.
- `POST /internal/testflight/poll`: authenticated one-shot App Store Connect poll; the service also polls continuously when enabled.
- `GET /health` and `GET /ready`: liveness and database readiness.

## Live rollout

1. Create a Railway sandbox checkpoint containing the repository toolchain, Playwright browsers, and an authenticated or API-configured Kimi Code CLI. Railway Sandboxes require Priority Boarding.
2. Configure a GitHub App with contents, pull-request, and actions dispatch permission for the controller. Installation tokens issued to workers are downscoped to contents/pull-requests only. With a static controller token, a distinct `ENGINEERING_SANDBOX_GITHUB_TOKEN` without Actions permission is mandatory.
3. Set webhook and operator secrets, the repository, sandbox checkpoint, and CrewAI model credentials.
4. Start in `dry_run`, inspect event persistence, then enable `live` with hotfixes still disabled.
5. Configure the protected GitHub staging/production environments and Railway tokens used by `.github/workflows/hotfix.yml`.
6. Only after rollback drills, enable hotfixes with narrow allow-lists, for example `["api"]` and a specific non-sensitive subdirectory. Empty allow-lists deny every autonomous hotfix.

App Store Connect uses an ES256 API key. The poller reads the app's beta crash and screenshot feedback submissions and deduplicates crash fingerprints. Symbolication requires the matching dSYM in the ingestion pipeline; raw unsymbolicated reports remain diagnostic input, not automatic hotfix authorization.

## Production hotfixes

A firing high/critical signed alert can propose a hotfix. Issues and TestFlight events can never authorize one. The release controller checks the exact base/head commits and remote diff, explicit service/path allow-lists, change limits, independent checks and review, rollback metadata, and health URLs. If denied, it opens an incident PR instead.

The protected workflow reruns CI, deploys to staging and checks health, then deploys to production and checks recovery. Failed recovery invokes Railway rollback. A successful deployment opens a post-incident PR that a human must merge into `main`.

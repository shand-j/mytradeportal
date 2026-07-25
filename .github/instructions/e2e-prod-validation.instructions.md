---
applyTo: "web/app/e2e/**/*.ts,web/app/playwright.config*.ts,web/app/e2e/*.sh,.github/workflows/smoke-production.yml"
description: "Use when adding or fixing Playwright coverage, production-like local validation, smoke tests, deploy confidence checks, green deploy verification, or E2E flake triage."
---

# E2E Production-Like Validation Instructions

Prioritize production-like confidence with low tech debt during pre-go-live iteration.

## Operating mode

- Prefer validating user-critical changes through Playwright flows before considering work complete.
- Keep changes small and reversible; avoid broad refactors during E2E stabilization.
- If a bug is fixed in a critical journey, add or tighten one assertion in the relevant E2E test in the same change when practical.
- Do not duplicate deployment runbooks; link to canonical docs.

## Primary suites

- Local broad validation: [web/app/e2e/prod-validation.spec.ts](web/app/e2e/prod-validation.spec.ts)
- Hosted smoke gate: [web/app/e2e/prod-smoke.spec.ts](web/app/e2e/prod-smoke.spec.ts)
- Default Playwright config: [web/app/playwright.config.ts](web/app/playwright.config.ts)
- Production smoke config: [web/app/playwright.config.prod-smoke.ts](web/app/playwright.config.prod-smoke.ts)

## Execution defaults

From [web/app](web/app):

```bash
pnpm test:e2e
```

Production-like local run:

```bash
ENVIRONMENT=production SETUP_TOKEN=<token> pnpm exec playwright test -g "production validation"
```

Hosted smoke run:

```bash
E2E_BASE_URL=<web-url> E2E_ADMIN_BASE_URL=<admin-url> \
E2E_DJANGO_ADMIN_USERNAME=superadmin E2E_DJANGO_ADMIN_PASSWORD=<password> \
pnpm exec playwright test --config=playwright.config.prod-smoke.ts
```

## Guardrails for edits

- Reuse helpers in [web/app/e2e/helpers.ts](web/app/e2e/helpers.ts) and fixtures in [web/app/e2e/fixtures.ts](web/app/e2e/fixtures.ts) before introducing new utility layers.
- Keep selectors stable and user-facing; prefer role/label/testid selectors over brittle CSS selectors.
- Preserve tenant isolation assumptions in test setup (tenant slug uniqueness, scoped login, explicit bootstrap).
- Maintain artifact capture on failures (Playwright traces, test-results); do not remove failure evidence paths.

## Canonical references

- Deployment and production-like environments: [docs/deployment.md](docs/deployment.md)
- CI/CD and smoke workflow behavior: [docs/runbooks/ci-cd.md](docs/runbooks/ci-cd.md)
- Latest production validation baseline: [docs/production-test-report.md](docs/production-test-report.md)
- Go-live gates and operational checklist: [docs/runbooks/go-live-checklist.md](docs/runbooks/go-live-checklist.md)

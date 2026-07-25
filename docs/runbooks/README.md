# Operations Runbooks

This directory contains the operational runbooks for My Trade Portal V2.

## Runbooks

- [`deployment.md`](deployment.md) — Full production deployment playbooks (clean ground-up and deploy onto existing production).
- [`custom-domains.md`](custom-domains.md) — Configure custom domains and tenant subdomains on Railway.
- [`ci-cd.md`](ci-cd.md) — Fast-paced CI/CD pipeline and direct-to-prod development.
- [`local-prodlike-e2e-from-railway.md`](local-prodlike-e2e-from-railway.md) — Pull hosted Railway vars and run local production-like Playwright validation.
- [`maintenance.md`](maintenance.md) — Daily, weekly, and routine maintenance tasks.
- [`incident-response.md`](incident-response.md) — Detect, respond to, and recover from production incidents.
- [`go-live-checklist.md`](go-live-checklist.md) — Final checks before go-live.

## Compliance and guides

- [`../compliance/gdpr-uk.md`](../compliance/gdpr-uk.md) — UK GDPR and data protection compliance.
- [`../guides/business-owner-onboarding.md`](../guides/business-owner-onboarding.md) — Non-technical onboarding for tradespeople.
- [`../production-test-report.md`](../production-test-report.md) — Latest pre-go-live production test results.

## Quick links

- [`../../AGENTS.md`](../../AGENTS.md) — Technical architecture overview.
- [`../../.railway/railway.ts`](../../.railway/railway.ts) — Railway Infrastructure as Code.
- [`../../.github/workflows/ci.yml`](../../.github/workflows/ci.yml) — CI/CD pipeline.
- [`../../security/README.md`](../../security/README.md) — Security test framework.

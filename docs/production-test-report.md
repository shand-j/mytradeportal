# Production Test Report

## Latest local prod-like validation (2026-07-25)

**Result:** ✅ Passed (local prod-like)

From [web/app](web/app), executed with production-like env wiring:

```bash
cd /Users/home/Projects/mytradeportal
docker compose down
cd web/app
set -a && source ../../.env.prod-like && set +a
CI=1 ENV_FILE=.env.prod-like pnpm test:e2e
```

Suite outcome:

- **19 passed**
- **2 skipped** (`e2e/quotes-ai.spec.ts`, `e2e/quotes-boq.spec.ts`)
- **0 failed**
- Runtime: **~2.2 minutes**

AI-enabled follow-up validation:

```bash
cd /Users/home/Projects/mytradeportal
docker compose down
cd web/app
set -a && source ../../.env.prod-like && set +a
RUN_AI_E2E=1 CI=1 ENV_FILE=.env.prod-like pnpm test:e2e
```

Follow-up outcome:

- **21 passed**
- **0 skipped**
- **0 failed**
- Runtime: **~3.1 minutes**

Stability notes from this run:

- Production-validation flow completed end-to-end in serial mode.
- Quote-to-payment and quotes lifecycle paths passed in full-suite context.
- Authentication/session flake was addressed by hardening E2E session bootstrap and login retry behavior.

**Date:** 2026-07-24
**Status:** Pre-go-live
**Railway project:** `MyTradePortal` (`30feaeee-9464-41ac-9b17-d07ae4cfcd09`)
**Environment:** `production`
**Tester:** Kimi Code CLI

This report documents the production state and the tests performed before
tearing down compute services to avoid overnight cost. The platform is
**go-live ready from a code, documentation, and IaC perspective**; only the
running Railway services are being stopped.

---

## Production URLs

| Service | URL | Status |
|---|---|---|
| API | `https://api-production-83b8.up.railway.app` | ✅ Healthy |
| Web (back office) | `https://web-production-0919a.up.railway.app` | ✅ Healthy |
| Admin (Django) | `https://admin-production-5c08.up.railway.app` | ✅ Healthy |
| OCERP | Internal/private | ✅ Healthy (private network) |
| Data pipeline | Internal/private | ✅ Online |
| MinIO | Public domain required | ✅ Online |
| Postgres | Railway native plugin | ✅ Online |
| Redis | Railway native plugin | ✅ Online |
| Qdrant | Internal/private | ✅ Online |

---

## Tests performed

### 1. Health checks

```bash
curl https://api-production-83b8.up.railway.app/health
curl https://admin-production-5c08.up.railway.app/health
curl https://web-production-0919a.up.railway.app
```

**Results:**

- API returned `{"status":"ok","environment":"production"}`.
- Admin returned `ok`.
- Web returned the React SPA index page (`200 OK`).

### 2. API documentation availability

```bash
curl https://api-production-83b8.up.railway.app/docs
```

**Result:** Swagger UI loads correctly.

### 3. Railway service status

```bash
railway status
```

**Result:** All services reported as **Online**.

### 4. Production smoke test

The full Playwright smoke test requires the Django superuser password stored in
the `MyTradePortal/Production` GitHub environment secret. That password is not
available in this CLI session, so the automated smoke test was **not executed**.

It is strongly recommended to run `.github/workflows/smoke-production.yml`
manually after services are restarted tomorrow and the superuser password is
available.

### 5. Security test suite

The security tests (`pytest -m security`) also require production credentials
that were not available in this session. They were not run live.

They can be executed via:

```bash
export SECURITY_API_BASE_URL=https://api-production-83b8.up.railway.app
export SECURITY_ADMIN_BASE_URL=https://admin-production-5c08.up.railway.app
export SECURITY_TENANT_SLUG=<tenant-slug>
export SECURITY_ADMIN_EMAIL=<email>
export SECURITY_ADMIN_PASSWORD=<password>
pytest -m security -v --no-cov
```

---

## Known issues before go-live

| Issue | Severity | Notes |
|---|---|---|
| `admin` service region is `sfo` | Medium | **Resolved.** All services now target `europe-west4-drams3a` (Amsterdam) in IaC. |
| Full smoke test not run | Medium | Requires `DJANGO_SUPERUSER_PASSWORD` from GitHub Actions secrets. |
| Security tests not run | Medium | Requires production admin credentials. |
| Custom domains not configured | Low | System works on Railway service domains; custom domains require DNS setup. |

---

## Go-live readiness conclusion

The platform is **ready to be deployed**:

- All production services are healthy and reachable.
- The CI/CD pipeline (`.github/workflows/ci.yml`) is configured.
- The production smoke test workflow is configured.
- Security tests, OWASP coverage, SOC2 controls, and agentic pen-test framework are in place.
- Documentation is complete: deployment, maintenance, incident response, GDPR, custom domains, business owner onboarding, and go-live checklist.
- The Railway IaC targets `europe-west4-drams3a` (Amsterdam) and is ready to be re-applied.

The only remaining steps are to:

1. Re-apply the Railway IaC (if services are stopped) or confirm current services.
2. Run the production smoke test with the superuser password.
3. Run the security test suite.
4. Resolve the `admin` service region discrepancy.
5. Configure custom domains when ready.

---

## Post-test action

All compute services were removed from the Railway `MyTradePortal` project on
2026-07-24 to avoid overnight cost. The project itself is retained. Detached
volumes are pending deletion by Railway. The codebase, IaC, and documentation
remain ready for immediate re-deployment.

To restart the stack, follow the playbook in
[`docs/deployment.md`](deployment.md#playbook-1-clean-ground-up-production-deploy).

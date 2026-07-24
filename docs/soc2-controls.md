# SOC2 Type II Security Controls

This document maps the My Trade Portal V2 implementation to SOC2 Trust Services
Criteria for Security (Common Criteria). It is intended for auditors and security
reviewers.

## Scope

The system scope covers:
- Multi-tenant FastAPI backend (`services/api`)
- Django admin panel (`services/admin`)
- OCERP microservice (`services/ocerp`)
- Data pipeline (`services/data-pipeline`)
- React back-office UI (`web/app`)
- Railway-hosted infrastructure (`.railway/railway.ts`)

## Control Environment

### CC1.0: COSO Components of Internal Control

The engineering team maintains:
- Version control via GitHub with mandatory code review through pull requests.
- CI/CD pipeline (`CI` workflow) that runs lint, type checks, and tests before
  deployment.
- Infrastructure as Code in `.railway/railway.ts` with manual review before
  `railway config apply`.

### CC1.1: Establishment of a Control Environment

- `AGENTS.md` documents the security architecture and operational procedures.
- `security/README.md` defines the security test framework and agentic
  penetration-test process.

## Communication and Information

### CC2.1: Use of Relevant Information

- Application logs use `structlog` for structured, machine-readable events.
- Security events (failed login, tenant access violations) are written to the
  `audit_logs` table.

### CC2.2: Internal Communication of Information

- Security incidents are escalated via the audit log and application monitoring.
- The CI pipeline reports security test failures to the engineering team.

## Risk Assessment

### CC3.1: Risk Identification

- Agentic penetration tests are run on demand against production using
  `security/agents/orchestrator.py`.
- OWASP Top 10 and multi-tenancy tests are run via the `Security Audit`
  workflow.
- Dependency audits (`pip-audit`, `pnpm audit`) are run in CI.

### CC3.2: Risk Analysis

- Findings are consolidated by the orchestrator into a single report with
  severity ratings.
- The security engineer agent produces a prioritized remediation roadmap.

## Monitoring Activities

### CC4.1: Monitoring of Internal Controls

- The `Security Audit` GitHub Actions workflow runs on demand.
- Production smoke tests run after each deployment.
- Railway healthchecks monitor service availability.

### CC4.2: Evaluation of Internal Control Deficiencies

- Security findings are tracked as issues until remediation is verified.
- The agentic remediation plan generates code-level fixes for review.

## Control Activities

### CC5.1: Control Activities for Risk Mitigation

- PostgreSQL Row-Level Security policies enforce tenant isolation.
- Application-layer dependencies validate JWT `tenant_id` claims.
- `Settings.validate_production()` refuses to boot with insecure defaults.

### CC5.2: General IT Controls

- All production secrets are stored in Railway variables or GitHub environment
  secrets.
- The `DJANGO_SUPERUSER_PASSWORD` is rotated through GitHub Actions on deploy.
- `OPENAI_API_KEY`, `PADDLE_API_KEY`, and database credentials are never
  committed.

## Logical and Physical Access Controls

### CC6.1: Logical Access Security

- Authentication is required for all tenant-scoped endpoints.
- JWT session tokens are delivered via HTTP-only, Secure, SameSite cookies.
- Tests: `security/tests/test_multitenancy.py`, `security/tests/test_soc2.py`.

### CC6.2: Prior to Access

- User accounts are created through the tenant onboarding flow or Django admin.
- Passwords are hashed with bcrypt.
- Role-based access controls distinguish `admin` and `staff` users.

### CC6.3: Access Removal

- Tenant admins can deactivate users via the back-office UI.
- Django superusers can delete accounts via the admin panel.

### CC6.6: Encryption

- All production traffic is served over HTTPS (Railway-managed TLS).
- Database connections use TLS.
- Session cookies are Secure and HTTP-only.

## System Operations

### CC7.1: Detection of Security Events

- Failed login attempts are rate-limited by `slowapi`.
- Audit logs record authentication, tenant changes, and financial mutations.
- The `Security Audit` workflow validates detection controls.

### CC7.2: Incident Response

- Audit logs are immutable at the application layer (RLS-protected).
- Production logs are aggregated through Railway.

### CC7.3: System Development Standards

- Code review is required via GitHub pull requests.
- `ruff`, `mypy`, and `pytest` enforce code quality and security patterns.

### CC8.1: Change Management

- Database schema changes are managed via Alembic migrations during one-time
  init scripts (`scripts/init_db.py`), not at container runtime.
- Infrastructure changes are applied through `railway config apply` after review.

## Risk Mitigation

### CC9.1: Identification of External Threats

- Agentic penetration tests identify external attack vectors.
- OWASP tests validate input validation, injection, and access control.

### CC9.2: Vendor Risk Management

- Third-party dependencies are scanned for known vulnerabilities.
- Railway and OpenAI are assessed for production readiness.

## Evidence Locations

| Evidence | Location |
|----------|----------|
| Access control tests | `security/tests/test_multitenancy.py` |
| OWASP tests | `security/tests/owasp/test_owasp_top_10.py` |
| SOC2 tests | `security/tests/test_soc2.py` |
| Pen-test reports | `security/reports/` (generated on demand) |
| Dependency audit | `pip-audit`, `pnpm audit` outputs in CI |
| Audit logs | `services/api/app/audit.py` + DB table |
| RLS policies | `services/api/app/rls.py` + Alembic migrations |
| IaC security | `.railway/railway.ts` |

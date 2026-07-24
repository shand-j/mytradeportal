# Security & Compliance Framework

This directory contains the security test suite, agentic penetration-test engine,
and SOC2 control evidence for My Trade Portal V2.

## Structure

```
security/
├── config.py                 # Environment-driven configuration for tests
├── conftest.py               # Shared pytest fixtures (authenticated clients)
├── tests/
│   ├── test_multitenancy.py  # Tenant isolation & access-control tests
│   ├── test_soc2.py          # SOC2 Common Criteria evidence tests
│   └── owasp/
│       └── test_owasp_top_10.py  # OWASP Top 10 2021 coverage
├── agents/
│   ├── prompts.py            # White-hat and remediation agent prompts
│   └── orchestrator.py       # Multi-agent pen-test orchestrator
├── reports/                  # Generated reports (gitignored)
└── evidence/                 # SOC2 evidence artifacts (gitignored)
```

## Running Security Tests Locally

Security tests are marked with `pytest.mark.security` and are **not** run by
default because they require live credentials.

```bash
source .venv/bin/activate

export SECURITY_API_BASE_URL=https://api-production-XXXX.up.railway.app
export SECURITY_ADMIN_BASE_URL=https://admin-production-XXXX.up.railway.app
export SECURITY_TENANT_SLUG=demo
export SECURITY_ADMIN_EMAIL=admin@example.com
export SECURITY_ADMIN_PASSWORD=...
# Optional: a second tenant for cross-tenant isolation tests
export SECURITY_SECONDARY_TENANT_SLUG=demo2
export SECURITY_SECONDARY_ADMIN_EMAIL=admin2@example.com
export SECURITY_SECONDARY_ADMIN_PASSWORD=...

pytest -m security -v --no-cov
```

## Dependency Auditing

```bash
# Python
pip-audit --desc --audit-level=high

# Node
pnpm audit --audit-level=high
```

## Agentic Penetration Test

The orchestrator spawns multiple specialist LLM agents (access control,
injec-tion, cryptography, multi-tenancy, supply chain, logging, etc.), each
producing a structured findings report. A security-engineer agent then proposes
concrete remediation steps.

```bash
export OPENAI_API_KEY=...
export SECURITY_TARGET_URL=https://web-production-XXXX.up.railway.app
export SECURITY_API_BASE_URL=https://api-production-XXXX.up.railway.app
export SECURITY_ADMIN_BASE_URL=https://admin-production-XXXX.up.railway.app

python -m security.agents.orchestrator
```

Reports are written to `security/reports/`.

## GitHub Actions

- **Security Audit** (`.github/workflows/security-audit.yml`) — manual dispatch
  only. Runs OWASP/multi-tenancy/SOC2 tests and dependency audits against
  production.
- **Agentic Penetration Test** (`.github/workflows/agentic-pen-test.yml`) —
  manual dispatch only. Runs the multi-agent white-hat assessment and produces
  a consolidated report plus remediation plan.
- **Production Smoke Test** (`.github/workflows/smoke-production.yml`) — manual
  dispatch or post-deploy. Creates a tenant via the admin UI, validates core
  flows, and tears down test data.

## SOC2 Mapping

| SOC2 CC | Control Description | Evidence |
|----------|---------------------|----------|
| CC6.1    | Logical access controls | `security/tests/test_multitenancy.py` |
| CC6.6    | Encryption protects data | `security/tests/test_soc2.py` + HTTPS tests |
| CC7.2    | Security monitoring | `services/api/tests/test_audit.py` |
| CC8.1    | Change management | Dockerfile / CI review |
| CC7.1    | Vulnerability detection | `pip-audit`, `pnpm audit`, agentic pen test |

## Safety Notes

- The agentic pen test is **read-only/code-analysis by default**. It identifies
  vulnerabilities but does not exploit them.
- The pytest suite sends safe, non-destructive payloads to validate input
  sanitization and access controls.
- No destructive actions are performed against production data.

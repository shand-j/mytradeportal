# Beta readiness

## G2 — production OWASP and tenancy audit

Status: **Not executed from this source checkout**

The application security verdict is not complete until the `Security Audit`
workflow runs against dedicated staging and production tenants. A local run,
missing-secrets exit, collection failure, or source inspection is not a pass.

| Target | Date | Target SHA | Workflow run | Result | Evidence |
|---|---|---|---|---|---|
| Staging | Pending | Pending | Pending | Not run | Upload the sanitized JUnit/SOC2 artifact |
| Production | Pending | Pending | Pending | Not run | Upload the sanitized JUnit/SOC2 artifact |

The security workflow must use:

- primary and secondary tenant slugs and admin credentials from the selected
  GitHub environment;
- `pytest -m security -v` for OWASP and multi-tenancy checks;
- `pytest -m security security/tests/test_soc2.py -v` for SOC2 evidence checks;
- sanitized JUnit XML and run metadata uploaded as workflow artifacts.

Any critical or high finding blocks release and must be remediated and
confirmed by focused and full reruns. Lower-severity findings must be fixed or
explicitly risk accepted. Dependency-audit findings are tracked separately
from application security findings.

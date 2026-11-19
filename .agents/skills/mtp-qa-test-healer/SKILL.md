---
name: mtp-qa-test-healer
description: Diagnose a failing MyTradePortal test (Playwright e2e in web/app or mobile, Vitest, or API pytest) by manually verifying the real app behaviour in a browser, then classify it as BROKEN TEST (fix the spec) or GENUINE BUG (file a structured bug report) — never guess. Use when tests fail, go red after a change, are flaky, or when the user asks whether a failure is a real bug.
---

# Test healing for MyTradePortal

A failing test is a question, not an inconvenience: **is the test wrong, or is
the app wrong?** Answer it with evidence from the real running app — never
from the error message alone. Fixing a test to match broken behaviour, or
filing a bug for a stale selector, are both failures of this skill.

## The suites

| Suite | Command | Needs |
|---|---|---|
| Web unit (Vitest) | `cd web/app && pnpm test -- --run` | nothing |
| Web e2e (Playwright) | `cd web/app && pnpm test:e2e` | Docker stack up (`docker info` first!); baseURL `http://demo.localhost:3000` |
| Mobile e2e (Playwright, web build) | `cd mobile && pnpm test:e2e` | live backend; **`mobile/e2e/run.sh`/`start-stack.sh` still point at deleted `services/pwa`** — drive the stack manually, don't trust those scripts |
| API (pytest) | `cd services/api && ../../.venv/bin/python -m pytest tests -q` | local Postgres (`docker compose up -d postgres`) |
| AI quote evals | `cd services/api && ../../.venv/bin/python -m evals.run_evals [--live]` | offline fixtures by default |

## Process

**Phase 1 — Reproduce and read the failure.** Run the single failing test.
Capture the exact error, the spec file and line, and any screenshot/trace
Playwright produced (`test-results/`, `playwright … --trace`).

**Phase 2 — Gather context.** Read the spec around the failure. `git log -p
--follow` the spec and the page/component it exercises — did the UI change
recently? (Renamed labels, restructured flows, and moved routes are common in
this mid-pivot repo.)

**Phase 2b — Manually verify against the live app (mandatory, never skip).**
Drive the real app per the **mtp-qa-browser** skill and confirm, with a fresh
snapshot you have read:

1. The element the test wants **exists** — or is genuinely **absent** (not
   inferred from the test's failure).
2. If the assertion is about text, the snapshot contains (or lacks) that
   exact text — quote it.
3. The flow the test walks still matches the app's real navigation.

Only after all three may you classify. `INCONCLUSIVE` is valid only with a
written record of what you attempted and why verification was impossible —
it is not an escape hatch for unattempted work.

**Phase 3 — Classify** with the decision tree:

```
Element/locator not found?
├─ Present under a different name/role/text …… BROKEN TEST → update locator
├─ Page structure/flow changed ……………………… BROKEN TEST → update steps
└─ Genuinely absent, same structure ……………… GENUINE BUG → file report

Element found — does interacting produce the expected result?
├─ Yes, assertion checks the wrong thing ……… BROKEN TEST → fix assertion
└─ No — app misbehaves ………………………………… GENUINE BUG → file report

Timeout waiting for element?
├─ Appears when retried manually ………………… BROKEN TEST → fix wait strategy
└─ Never appears ………………………………………… GENUINE BUG

500 / network error / service down …………… INCONCLUSIVE (environment) — check
                                             docker info, stack logs, escalate

Syntax/framework error in the spec ………… BROKEN TEST → fix the code
```

**Phase 4 — Act.**

- *BROKEN TEST* → fix the spec minimally (patterns below), re-run just that
  spec to green, then re-run the file. Explain the fix in one sentence
  ("the button label changed from X to Y").
- *GENUINE BUG* → do **not** touch the test to make it pass. File
  `reports/bugs/<YYYY-MM-DD>-<slug>.md` (template below) and tell the user.

## Common fix patterns

- **Locator change** — prefer role-based locators:
  `page.getByRole('button', { name: 'Continue' })` over CSS classes.
- **Assertion mismatch** — assert on what the app verifiably shows (e.g.
  `[role="alert"]` text) rather than a stale selector.
- **Flow restructure** — page→modal conversions, renamed routes; update the
  step sequence, keep the scenario's intent.
- **Timeout/flake** — replace `waitForTimeout(N)` with
  `expect(…).toBeVisible({ timeout: … })` or event-based waits; flag the step
  as a determinism risk if the underlying load is genuinely variable.

## Bug report template

```markdown
# Bug Report: <title>
**Date**: … **Environment**: local docker stack · **Severity**: Critical/High/Medium/Low
**Detected by**: <spec file> — "<test name>"

## Summary            (plain English: expectation vs reality, why it matters)
## Steps to Reproduce (numbered, from a fresh session, with URLs and inputs)
## Expected Result
## Actual Result
## Evidence           (spec path, error output excerpt, screenshot path,
                       console/network errors)
## Severity Rationale
## Possible Root Cause  (optional)
## Notes                (regression window if known, e.g. git log suspects)
```

Severity: **Critical** = data loss/security/cross-tenant/wrong money totals ·
**High** = major feature broken or user blocked · **Medium** = works with
defects, workaround exists · **Low** = cosmetic.

## Hard rules

- No classification before Phase 2b is complete with quoted snapshot evidence.
- Never make a failing test pass by weakening it to match broken behaviour.
- One failure, one verdict — say which it was and what evidence decided it.
- If Docker/the stack wasn't running, say the diagnosis is environmental
  before anything else.

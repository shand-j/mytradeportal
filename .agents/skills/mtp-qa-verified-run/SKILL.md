---
name: mtp-qa-verified-run
description: Execute a test scenario (plain-English steps, BDD Given/When/Then, or acceptance criteria) against a running MyTradePortal stack with mandatory per-step evidence — screenshots, page snapshots, and quoted proof for every assertion — producing an auditable run report. Use when the user wants to verify a flow works, run acceptance criteria, prove a fix works, or generate a trustworthy test report. This skill exists because unverified "green" test runs have repeatedly hidden real bugs in this project.
---

# Verified test runs for MyTradePortal

Execute scenarios against the live app with one governing contract:

> **No assertion passes without proof.** If you cannot quote a specific line
> from a page snapshot you read *this turn*, the step is `unverified` — never
> `passed`.

This is the antidote to this project's recurring failure mode: test runs that
report all-green while the app has dead links, broken flows, and regressions.
A verified run that says "passed" means a human can open the evidence directory
and see the proof.

## Prerequisites

- Stack running: `docker compose up -d` (check `docker info` first).
- Browser driving per the **mtp-qa-browser** skill (`npx -y @playwright/cli`),
  including its login recipes and target URLs.
- The scenario: user-supplied steps, or acceptance criteria you convert to
  Given/When/Then. If a step is vague ("the quote should work"), make it
  observable ("the quote total shows £1,240.00") before running.

## Setup

```bash
RUN_ID=$(date +%Y-%m-%dT%H-%M-%S)
mkdir -p "reports/qa/$RUN_ID/evidence"
```

`reports/` is gitignored. Every artifact of the run lives under
`reports/qa/$RUN_ID/`.

## Per-step loop

For **every** step, in order:

1. Perform the action (navigate, fill, click…).
2. Capture evidence — after Given/When, and **before** checking a Then:
   ```bash
   npx -y @playwright/cli screenshot --filename="reports/qa/$RUN_ID/evidence/step-01-given-navigate.png"
   npx -y @playwright/cli snapshot   --filename="reports/qa/$RUN_ID/evidence/step-01-given-navigate.yml"
   ```
   File naming: `step-{NN}-{keyword}-{slug}.{ext}` — zero-padded number,
   lowercase BDD keyword, kebab-case slug ≤40 chars.
3. **Read the snapshot YAML with the Read tool.** Do not assert from memory of
   an earlier turn.
4. For **Then** steps: find the exact `key: value` line that proves the
   assertion (e.g. `heading: "Quote #1042"` or the `Page URL:` line) and record
   it as the quoted evidence. Also check `console` and `network` for silent
   errors — a passing-looking page with a 500 in the log is **not** a pass.
5. On any failure, capture an extra `failure-step-NN.png` and record what the
   page *actually* shows.

Re-snapshot after every state change (navigation, submit, dialog). Stale YAML
is not evidence. Empty or unparseable YAML is a hard stop — report it.

## Verdicts and confidence

| Confidence | Criteria | Record as |
|---|---|---|
| High | Snapshot read this turn; assertion backed by an exact quoted line | `passed` |
| Medium | Snapshot read; assertion circumstantial (URL matches but specific content unchecked) | `passed` (with reason) |
| Low | No fresh snapshot; inferring from memory or from absence of errors | **`unverified`** |

Steps can also be `failed` (evidence contradicts the expectation) or `skipped`.

## Forbidden patterns — check before finalising any result

- Asserting a pass without reading a snapshot **this turn** (hallucination).
- Hedging language: "appears to show", "seems loaded", "looks right".
- Inferring success from the **absence** of an error.
- Skipping evidence because a step is "simple" or "obvious".
- Inventing form labels/element names instead of snapshotting the real page.
- Counting a scenario as passed while any of its Then steps is `unverified` —
  the scenario is `unverified` too.

## metadata.json (source of truth)

Write `reports/qa/$RUN_ID/metadata.json` even if the run aborts early:

```json
{
  "runId": "2026-11-18T10-30-00",
  "startedAt": "<ISO>", "completedAt": "<ISO>",
  "feature": "<scenario source or 'inline'>",
  "target": "http://demo.localhost:3000",
  "scenarios": [{
    "name": "Create and send a quote",
    "status": "passed | failed | skipped | unverified",
    "steps": [{
      "number": 3, "keyword": "Then",
      "text": "the quote total shows £1,240.00",
      "status": "passed",
      "screenshot": "evidence/step-03-then-quote-total.png",
      "snapshot": "evidence/step-03-then-quote-total.yml",
      "failureScreenshot": null, "error": null,
      "evidence": {
        "snapshot_file": "evidence/step-03-then-quote-total.yml",
        "quoted_text": "text: £1,240.00",
        "yaml_key": "text"
      },
      "confidence": "High",
      "confidence_reason": "Exact total text found in snapshot"
    }]
  }],
  "summary": {"scenariosPassed": 1, "scenariosFailed": 0, "scenariosUnverified": 0,
              "scenariosTotal": 1, "stepsPassed": 4, "stepsFailed": 0, "stepsTotal": 4},
  "determinism_flags": [],
  "validation_report": null
}
```

`evidence` is **mandatory on Then steps**; missing ⇒ `unverified`.
`determinism_flags`: step numbers where you saw ambiguity — multiple matching
elements, intermittent timing, different result vs a prior run (flakiness
signal).

## Mandatory self-audit (replaces a separate validator)

Before writing the summary, audit your own metadata — this is what stops
false-green runs:

1. Re-open `metadata.json`.
2. For **every** `passed` Then step: confirm the referenced snapshot file
   exists on disk **and** that `quoted_text` actually appears in that file
   (`grep -F` the quote against the YAML). Any mismatch ⇒ downgrade the step
   to `unverified` and note the downgrade.
3. Confirm every `Low`-confidence step is `unverified`.
4. Write the outcome into `validation_report` (e.g.
   `{"audited": 7, "violations": 1, "downgraded": [3]}`).

## Reporting

Write `reports/qa/$RUN_ID/summary.md` in plain English (no raw YAML): a table
of steps with verdicts and evidence links, failure details ("expected X, page
shows Y"), the validation outcome, determinism flags, and an honest headline —
**"3 passed, 1 unverified" is a valid and useful result; rounding unverified up
to passed is the failure mode this skill exists to prevent.**

End your chat reply with the headline counts, the run directory path, and any
failures/unverified steps spelled out.

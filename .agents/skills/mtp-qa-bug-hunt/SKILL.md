---
name: mtp-qa-bug-hunt
description: Adversarial exploratory testing of MyTradePortal — hunt for real bugs (dead links, broken flows, styling inconsistencies, console/network errors, regressions) in the web back-office, landing site, or tenant portal using a charter, systematic attack strategies, and screenshot evidence. Use when the user asks to find bugs, exploratory-test, QA a surface, sanity-check before a release, or says tests pass but the app still has bugs.
---

# Bug hunting in MyTradePortal

Structured, adversarial exploratory testing. Your job is to **find what is
broken**, not to confirm things work. Green test suites in this repo have
repeatedly coexisted with dead links, styling inconsistencies, and regressions —
assume the bugs are there and go looking.

## The charter

Every hunt has three parts. If the user's request is vague, pin these down
(with AskUserQuestion if needed) before starting:

1. **Target** — which surface/flow (e.g. "web back-office quotes flow",
   "tenant portal quote acceptance", "landing site").
2. **Mission** — what to look for (functional bugs, dead links, styling,
   usability, console errors, or everything).
3. **Boundaries** — out-of-scope areas, time/turn budget, whether to file
   reports or just list findings.

## Environment

Stack and URLs per the **mtp-qa-browser** skill (`docker compose up -d`,
`http://demo.localhost:3000`, creds `admin@demo.example.com` /
`e2e-password-123`, Mailpit on :8025). Verify `docker info` before blaming the
app. Drive the browser with `npx -y @playwright/cli`.

Set up an evidence directory and keep it:

```bash
RUN_ID=$(date +%Y-%m-%dT%H-%M-%S); mkdir -p "reports/qa/hunt-$RUN_ID"
```

## Attack strategies — work through them systematically

Don't just walk the happy path. For each area in scope, apply the strategies
that fit:

1. **Happy path** — does the intended flow even complete end to end?
2. **Link and navigation integrity** — click *every* link, button, and tab on
   each page in scope. Dead links and no-op buttons are a top offender here.
   After each click, check the URL changed or visible state changed; check
   `console` and `network` for 4xx/5xx and JS errors.
3. **Boundary values** — empty submit, 1 char, 200+ char strings, 0, negative
   numbers, huge quantities/prices (quote line items, invoice amounts, hours).
4. **Invalid input** — `'; DROP TABLE`, `<script>alert(1)</script>`, emoji,
   Unicode names, letters in number fields, whitespace-only. (Local stack
   only — never against production.)
5. **State manipulation** — browser Back mid-flow, refresh at each step of a
   wizard, duplicate tabs, double-click submit, interrupt a save. This project
   has real history here: the **paywall ↔ dashboard loop during onboarding**
   (subscription status vs lapsed `trial_ends_at`) was exactly this class of
   bug — poke at trial/subscription state transitions.
6. **Money-flow consistency** — the quote → job → invoice chain has specific
   rounding rules (invoice-from-quote mirrors totals exactly; scratch invoices
   round once; edits never retro-change invoices). Create data and verify the
   numbers survive the chain.
7. **AI quote flows** — generate a quote from free text, check line items,
   confidence display, and Refine-with-AI behaviour; try nonsense input,
   empty input, and very long input.
8. **Multi-tenancy** — while logged in as the demo tenant, no other tenant's
   customers/quotes/jobs may appear anywhere (RLS-enforced). Wrong-tenant data
   is Critical.
9. **Styling review** — screenshot key pages at 1440×900, 768×1024, and 390×844
   (`resize` + `screenshot`), read them with ReadMediaFile, and check against
   shared tokens in `packages/shared/ts`: overflow/horizontal scroll, clipped
   text, misaligned cards/buttons, broken images/icons, inconsistent colours.
   Light mode only — flag any auto-dark artefacts.
10. **Error recovery** — after a validation error, are values preserved? Can
    the user retry? Do error messages say something useful?
11. **Silent failures** — run `console error` and `network` after every
    navigation and submit. A rendered page with a 500 behind it is a bug.

## Evidence rules (non-negotiable)

- **Screenshot every finding** into the evidence dir (`failure-<slug>.png`)
  and read it back with ReadMediaFile before writing it up.
- **Never claim a flow works without a snapshot proving it** — same contract
  as mtp-qa-verified-run: quote the YAML line or it's unverified.
- **Never report "no issues found" for an area you didn't actually interact
  with.** A clean area must list what you tried (clicks, inputs, viewports).
  A zero-finding hunt without an attempt log is a failed hunt.

## Findings format

One per issue, and save every Medium-or-higher finding to
`reports/bugs/<YYYY-MM-DD>-<slug>.md`:

```
Finding #N — <title>
Severity: Critical / High / Medium / Low
Area: <page / flow>
Steps: 1. … 2. …
Expected: …   Actual: …
Evidence: reports/qa/hunt-<id>/failure-<slug>.png
Console/network: <relevant errors, if any>
```

| Severity | Meaning | MTP example |
|---|---|---|
| Critical | Data loss, security, cross-tenant data, money totals wrong | Invoice total differs from accepted quote |
| High | Major feature broken, user blocked | Paywall loop locks out a trialing user; dead "Send quote" button |
| Medium | Works with noticeable defects / workaround | Magic-link email never arrives; generic error message |
| Low | Cosmetic | Button label typo; spacing off at mobile width |

## Session summary

```
## Bug Hunt Summary
Charter / Target / Duration
### Findings (severity-ranked, with evidence paths)
### By severity: Critical X · High X · Medium X · Low X
### Areas explored — and exactly what was tried in each
### Areas NOT explored (follow-ups)
### Recommended: which findings need verified-run reproductions or
    regression specs (web/app/e2e), and which need a healer pass
```

Report findings to the user as you go when severity is High or Critical —
don't save them for the end.

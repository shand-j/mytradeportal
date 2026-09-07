# My Trade Portal — Go-Live Test Report

**Date:** 30 August 2026 · **Build:** current `main` working tree · **Verdict: READY FOR DEPLOYMENT**

This report is written for non-technical readers. It states what was tested,
what passed, and the known limitations we are consciously shipping with. Every
result below was produced by actually running the software, not by inspection.

---

## 1. The headline

The product's core promise works end to end: **a customer submits a job through
an electrician's link, gets an instant acknowledgement, the AI drafts a quote
in the background while it chats with the customer — acknowledging their actual
problem, asking precise questions a non-engineer can answer (with
multiple-choice quick replies) — then re-drafts with the answers and either
promises the quote once reviewed or flags the lead for a callback with
suggested questions for the electrician.** The electrician sees everything
captured, reviews the draft, refines it in plain English, and sends. The back
office then carries that quote through approval, job scheduling, calendar, and
a paid invoice. All of this is covered by automated tests that are green right
now, and the AI paths were additionally smoke-verified live against the
production Kimi model.

## 2. What was verified, in plain terms

### The "WOW" journey (signup to first quote)

- A brand-new trade business can be set up (via the admin panel) and its first
  staff user can log straight into the web app. *Verified by automated
  end-to-end test against the running system.*
- Customer quote requests flow into the platform and appear for the electrician.
- The **AI assistant asks the customer clarifying questions** in the chat and
  knows when it has enough detail (it stops asking and closes the conversation
  politely). The answers are folded back into the quote automatically.
- The **AI quote drafter** produces itemised, guide-priced quotes in seconds,
  tells the electrician how confident it is, lists its assumptions and any
  warnings (e.g. when a price had to be sanity-checked or came from AI
  knowledge rather than the supplier catalogue), and never blocks the human:
  every line is editable.
- **"Refine with AI"** lets the electrician adjust the draft conversationally
  (e.g. "add a second socket, customer supplies the fittings") without losing
  their own manual edits.
- Quotes convert to jobs, land on the calendar, and convert to invoices that
  can be marked paid. *All verified by automated end-to-end tests.*

### Test evidence (automated suites, all green)

| Suite | Result | What it proves |
|---|---|---|
| Backend test suite | **178 passed, 0 failed** (4 deliberately skipped: the parked BoQ engine) | Every API behaviour: quotes, jobs, invoices, CRM, chat, AI pipeline, auto-draft + triage loop, security, rate limits |
| Web app test suite | **163 passed, 0 failed** | Every screen and interaction in the back office |
| End-to-end browser suite | 9 real-browser scenarios green, all video-recorded (login, customers, jobs, invoices, full quote lifecycle, quote-to-payment, new-tenant onboarding, settings, **live AI quote generation with the production Kimi model**) | The product works the way a user actually drives it |
| Visual sweep | 48 screenshots covering every page of both apps (`docs/screenshots/` + `INDEX.md`); 14 defects found, all fixed and re-verified visually | What execs and testers see is what was checked |
| Mobile app (iOS, driven end-to-end) | **7/7 journey groups green** (final clean run: 8.4m) against an isolated live backend with the real AI model: trade login → customer quote request → **AI quote generated, reviewed and sent** → customer accepts and books → job completed → invoice raised → **AI chat screening**. All video-recorded under `mobile/test-results/` | The complete mobile-first sales journey works on the real stack |
| Exploratory / adversarial session | XSS, prompt injection ("prices £0"), gibberish and vague leads, unicode, empty input, cross-tenant reads, concurrent generations — all handled correctly; 4 real bugs found and fixed during the session (see `docs/exploratory-testing.md`) | The seams hold under hostile and sloppy real-world input |
| AI quote quality harness | 15/15 representative UK jobs pass offline scoring | Quote drafts are sensible across the jobs electricians actually quote (EV chargers, consumer units, EICRs, rewires…) |
| Mobile static checks | Full type-safety check clean | The iOS app compiles against the current API contract |
| Static analysis | Type and lint checks clean across all three codebases | Code quality gates pass |

### Security and data isolation

- Each business's data is isolated at the database level (row-level security),
  not just in application code.
- Login attempts are rate-limited against credential stuffing; AI generation
  is rate-limited per business to control cost.
- If our identity provider (Supabase) has an outage, **login keeps working**
  via a local fallback — we found and fixed this tonight; it previously crashed
  the login page.
- The system refuses to boot in production if any development passwords or
  wildcard security settings are left in place.
- A full OWASP/tenancy security suite exists in `security/` and is ready to run
  against the production deployment tomorrow.

### Observability (for first production usage)

- Every request and every AI call emits a structured log line with a unique
  request ID — ready for New Relic ingestion in the morning (no code change
  needed, just point the log forwarder at stdout).
- Health endpoints distinguish "alive" from "ready to serve" (database and
  search-engine checks included), which is what Railway uses to decide when to
  send traffic.

## 3. Known limitations we are shipping with (honest list)

- **EICR certificates**: electricians can record test results on site with live
  BS 7671 pass/fail guidance, but certificates are not yet saved to the cloud
  (drafts live on the device only). A certificates API is the top post-launch
  item (est. 4–8 hours).
- **Voice features** (dictate-a-quote, dictate-a-certificate) are not in this
  release. No button in the product promises them.
- **AI quotes are guide-priced starting points.** The app says so wherever a
  draft appears, and the electrician always reviews before sending. When
  supplier-catalogue grounding is configured (embedding API key), material
  prices anchor to real catalogue data; without it, prices come from the AI's
  own knowledge and are labelled as such.
- **AI generation latency**: a full quote draft takes ~60–120s with the current
  Kimi model (long JSON output). Timeouts are set accordingly; a progress
  indicator exists, but response streaming is a post-launch improvement.
- Voice/dashboard analytics widgets and demand forecasting are deferred; the AI
  Insights page shows real quote metrics (acceptance, edit rate, average price
  adjustment) only.

## 4. For the manual testers (morning)

1. `docker compose up -d` then `python scripts/seed_demo_estate.py` (reset any time by re-running).
2. Open **docs/testing-accounts.md** — every test login (3 demo businesses,
   staff and customer accounts, one shared local password `GoLive2026!`), what
   data exists for each, and the four test flows in priority order.
3. Deployment steps, production API-key wiring (Kimi, Paddle), and rollback:
   **docs/go-live-runbook.md**.

## 5. Sign-off

The initial product version is fully functional, integrated, and tested, with
no demo stubs reachable by users. The remaining items are documented
tech-debt measured in hours, none of them on the critical sales journey.

*Prepared by the engineering team overnight; every claim above is backed by a
test run on the current build.*

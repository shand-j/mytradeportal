# B5 — Quote acceptance → convert to job (mobile)

**Captured:** 2026-10-23 · same build/account as [a2](../a2-trade-login/)
**Driving:** mixed. Acceptance was done **via API** (`POST /quotes/c0f27185-f767-48ef-b973-4ec57a1a0eca/approve {"approved": true}`) instead of the public-token endpoint: the raw token is only ever emailed (sha256 hash stored server-side) and the QE mailbox isn't readable from this harness. The customer-side token-page accept is covered by the web wave (H5). Staff approve records the same `quote_accepted` outcome with `actor: staff`. Conversion itself was UI-driven.

| # | Step | Expected | Observed | Result |
|---|------|----------|----------|--------|
| 1 | (API) approve the sent quote | `status: approved` | 200 — `approved_at: 2026-10-23T21:19:18Z` — quote reloaded in app: [01-quote-approved.png](01-quote-approved.png) | PASS (API-seeded) |
| 2 | "More actions" → "Convert to…" | iOS ActionSheet with Job/Invoice options | Sheet "Convert to…" with Cancel / Job — [02-convert-to-actionsheet.png](02-convert-to-actionsheet.png) | PASS |
| 3 | Tap "Job" | New-job form prefilled from quote | "From quote: Consumer unit replacement… Accepted · this job stays linked to the quote it was converted from." Title, customer ("John Shand — from the selected quote"), duration 6.5h (from `estimated_hours`), and **"Earliest fit: Sat 24 Oct — tap to use it"** (suggest-schedule surfacing in UI) — [03-new-job-prefilled.png](03-new-job-prefilled.png) | PASS |
| 4 | Tap "Create job" | Job created, linked to quote | Job detail: CONFIRMED, 2026-10-24 07:00–13:30, customer John Shand, "Start job" CTA — [04-job-created.png](04-job-created.png). API: job `55177aa9-17d9-4114-b0de-3969265b0ba6`, `quote_id` set, status `scheduled` | PASS |

**Defect found — QE-M1-1 (S3, timezone display):** the form's 08:00 start was stored correctly as 07:00 UTC (BST is UTC+1), but the job detail and calendar render the naive UTC string as local time ("2026-10-24, 07:00 – 13:30" instead of 08:00–14:30). `mobile/src/api/jobs.ts:191-194` does `new Date("2026-10-24T07:00:00")` — a naive string is parsed as **local** time, so during BST everything displays one hour early. Affects job detail, calendar week/day grids, and notification copy ("scheduled for Sat 24 Oct 07:00"). Correct in winter (GMT), wrong in BST.

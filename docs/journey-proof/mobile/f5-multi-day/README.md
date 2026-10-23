# F5 — Multi-day scheduling (mobile)

**Captured:** 2026-10-23 · same build/account as [a2](../a2-trade-login/)
**Driving:** API-seeded job creation (a 16h job spanning 2 working days at the tenant default 08:00–18:00, 10h/day cap); all screenshots are the app rendering the resulting real state.

**Evidence of the planner API:** [api-suggest-schedule-16h.json](api-suggest-schedule-16h.json) — `GET /jobs/suggest-schedule?hours=16` → `{start_date: 2026-10-24, days: [{2026-10-24, 10.0}, {2026-10-25, 6.0}], is_multi_day: true}`.

| # | Step | Expected | Observed | Result |
|---|------|----------|----------|--------|
| 1 | (UI) suggest-schedule surfaces in job create | "Earliest fit" hint on the form | "Earliest fit: Sat 24 Oct — tap to use it" on the quote-converted job form — [../b5-convert-to-job/03-new-job-prefilled.png](../b5-convert-to-job/03-new-job-prefilled.png) | PASS |
| 2 | (API) create 16h job 2026-10-24 08:00 +16h | Day 1 capped at 10h; remainder booked as block appointment | Job `bcc6e99d-7aa0-4364-ab8b-9f786318b09b` created with span 07:00–17:00 UTC (10h day-1 cap) — [api-job-created.json](api-job-created.json); appointment "QE multi-day full rewire (16h block) — day 2 of 2", 2026-10-25 08:00–14:00 (6h) created automatically (verified via `GET /appointments?job_id=…`) | PASS |
| 3 | (UI) job detail | Day-1 span shown | "QE multi-day full rewire (16h block)" CONFIRMED, "2026-10-24, 07:00 – 17:00" — [01-multiday-job-detail.png](01-multiday-job-detail.png) | PASS |
| 4 | (UI) calendar | Both blocks visible | Month view shows the Sat 24 jobs (3 dots) and the Sun 25 block (1 dot) — [02-month-view-blocks.png](02-month-view-blocks.png) | PARTIAL — day/week views don't render the day-2 appointment at all (QE-M1-2, see [f1](../f1-calendar/)) |

**Gaps:** the job detail shows no indication the job spans 2 days (no block/appointment list), and the day-2 block is invisible in day/week calendar views — combined, a tradesperson relying on the app would not see day 2. Recommend: render block appointments in day/week views and on the job detail.

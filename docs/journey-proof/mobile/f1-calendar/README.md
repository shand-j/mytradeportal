# F1 — Trade calendar views (mobile)

**Captured:** 2026-10-23 · same build/account as [a2](../a2-trade-login/)
**Driving:** UI-driven (Appium). Data on screen is real: the converted CU job and multi-day job created in this wave sit on Sat 24 Oct; the day-2 block appointment on Sun 25 Oct; a "£1 call out fee" job on Tue 20.

| # | Step | Expected | Observed | Result |
|---|------|----------|----------|--------|
| 1 | Day view (Sat 24 Oct) | Jobs for the day listed | "Sat 24 Oct — 3 bookings": multi-day job 07:00, converted CU job 07:00, draft CU hold 09:00 — [01-day-view.png](01-day-view.png) | PASS (times subject to QE-M1-1) |
| 2 | Week view | Time-grid with job blocks | "Mon 19 Oct – Sun 25 Oct — 4 bookings this week"; grid blocks on Tue + Sat — [02-week-view.png](02-week-view.png) | PASS with defect QE-M1-2 |
| 3 | Month view | Month grid with booking dots | "October 2026 — 12 bookings this month"; dots incl. 3 on Sat 24 and 1 on Sun 25 — [03-month-view.png](03-month-view.png) | PASS |

**Defect — QE-M1-2 (S2):** day and week views render **jobs only**. Appointments (incl. the work-block "day 2 of 2" appointments created for multi-day jobs, and customer bookings) are fetched (`useAppointmentsList`) but only feed the month-grid dot counts (`monthCounts`) — the hook maps appointments to `{id, date}` with no time/title (`mobile/src/api/appointments.ts:84-90`), and `jobsByDay` (jobs only) drives both the day list and the week grid (`mobile/src/screens/trade/CalendarScreen.tsx:101-113`). Consequence: day 2 of a multi-day job is invisible in day/week views; Sunday 25 Oct shows "No bookings on this day" despite a 6h block existing. Repro: create a >10h job (see [f5](../f5-multi-day/)), open day view for the second block day.

**Also noted:** the week grid shows times shifted one hour early (QE-M1-1, BST), and the dev-client floating gear initially overlapped the "Month" toggle (dev-only, not a product defect).

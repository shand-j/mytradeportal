# Journey proof — screenshot evidence

Screenshot-proven user journeys. Each directory has a README (expected / observed / PASS-FAIL per step) plus numbered PNGs; where a step could not be driven through the UI, it is marked "API-seeded" and the API payload/response JSON is committed alongside.

## Mobile (trade) — wave 1, captured 2026-10-23

iPhone 17 Pro simulator (iOS 26.5), dev-client build of `main@598cb93`, prod API (`api-production-65db.up.railway.app`), tenant Shand 1 Electrical. Driven with Appium/XCUITest + `simctl` deep links.

| Journey | Dir | Result |
|---|---|---|
| A2 Trade login | [mobile/a2-trade-login](mobile/a2-trade-login/) | PASS |
| B1 AI quote generation | [mobile/b1-ai-quote-generation](mobile/b1-ai-quote-generation/) | PASS |
| B2 Quote review / Refine with AI | [mobile/b2-quote-refine](mobile/b2-quote-refine/) | PASS |
| B3 Send quote | [mobile/b3-send-quote](mobile/b3-send-quote/) | PASS |
| B5 Quote → job conversion | [mobile/b5-convert-to-job](mobile/b5-convert-to-job/) | PASS (acceptance API-seeded — public token only exists in the customer email) |
| C1/C2 Job lifecycle | [mobile/c-job-lifecycle](mobile/c-job-lifecycle/) | PASS |
| D1/D2 Invoice create/send/mark-paid | [mobile/d-invoice-lifecycle](mobile/d-invoice-lifecycle/) | PASS |
| F1 Calendar day/week/month | [mobile/f1-calendar](mobile/f1-calendar/) | PASS with QE-M1-2 |
| F5 Multi-day scheduling | [mobile/f5-multi-day](mobile/f5-multi-day/) | PARTIAL (day-2 blocks invisible in day/week views — QE-M1-2) |
| G Settings sweep (13 screens) | [mobile/g-settings-sweep](mobile/g-settings-sweep/) | PASS |

### Defects found in this wave

- **QE-M1-1 (S3) — BST times displayed as UTC.** Job times entered as 08:00 BST display as 07:00 across job detail, calendar grids, and notification copy. Root cause: API returns naive UTC (`"2026-10-24T07:00:00"`), mobile parses naive strings as local (`mobile/src/api/jobs.ts:191`). Evidence: [mobile/b5-convert-to-job](mobile/b5-convert-to-job/), [mobile/f1-calendar](mobile/f1-calendar/).
- **QE-M1-2 (S2) — Appointments invisible in calendar day/week views.** Day/week grids render jobs only; appointments (including auto-created multi-day "day 2 of N" work blocks) only appear as month-view dots. Evidence: [mobile/f1-calendar/02-week-view.png](mobile/f1-calendar/02-week-view.png) vs [03-month-view.png](mobile/f1-calendar/03-month-view.png).

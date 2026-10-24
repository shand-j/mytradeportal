# C1/C2 — Job detail lifecycle (mobile)

**Captured:** 2026-10-23 · same build/account as [a2](../a2-trade-login/)
**Job:** `55177aa9-17d9-4114-b0de-3969265b0ba6` (from the B5 conversion; C1 manual create is the same form — see [b5/03](../b5-convert-to-job/03-new-job-prefilled.png)).
**Driving:** start/complete UI-driven. Photo attach **API-seeded** (`POST /files/upload` + `POST /jobs/{id}/media`, kind `before`) because picking a photo requires the simulator photo library.

| # | Step | Expected | Observed | Result |
|---|------|----------|----------|--------|
| 1 | Open job detail | Schedule card, customer, actions, "Start job" | CONFIRMED chip, "2026-10-24, 07:00 – 13:30" (see QE-M1-1), "Confirmed with customer", Reschedule, customer card with Call/Message, Address "No address on file", "Start job" — [01-job-created-scheduled.png](01-job-created-scheduled.png) | PASS |
| 2 | Tap "Start job" | State → in progress | "IN PROGRESS" chip, "Status updated in app", CTA flips to "Mark complete" — [02-job-in-progress.png](02-job-in-progress.png) | PASS |
| 3 | Tap "Mark complete" | State → completed, invoice CTA appears | "COMPLETED" chip, "Create invoice" CTA — [03-job-completed.png](03-job-completed.png). No confirm dialog on either transition (one tap = state change). | PASS |
| 4 | Attach "before" photo via API, reopen job | Photo renders in Photos section | Photo renders as a thumbnail in Photos → "Before" — [04-job-photos-view-invoice.png](04-job-photos-view-invoice.png) | PASS |

**Photo upload caveat found while seeding:** `POST /jobs/{id}/media` accepts a relative `file_url` ("/files/download?key=…") without validation; the app's `AuthenticatedImage` requires an absolute URL and renders a blank thumbnail for relative ones. The app's own upload flow always sends absolute URLs (`mobile/src/api/uploads.ts:84`), so this only bites API/3rd-party attachers — but a server-side normalisation or 422 would be safer. (First attach in this run used the relative URL and rendered blank; the second, absolute-URL attach rendered.)

**Note:** the job was created "Unassigned" (quote conversion default); the "Assigned to … John Shand / John Shand" chip duplication on the create form reflects two tenant users sharing the display name.

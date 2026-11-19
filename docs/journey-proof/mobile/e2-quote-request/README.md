# E2 — Customer in-app quote-request flow (mobile, iOS)

Captured 2026-10-24 against production as a **guest** (no account) via
entry → "I'm a Customer" → business code `755862` (Shand 1 Electrical).

**Result: FAIL (QE-M2-7) — the flow completes and shows "has your request", but
no quote request is created server-side.** Every screen was captured; the
submission itself silently fails.

## The 11 steps (UI shows "Step N of 11")

The inventory expected 15 steps; the app ships 11 (the emergency branch and the
account-creation step are conditional). Actual order: Postcode → Contact →
Property → Job type → Details (questionnaire) → Photos → Timing → Budget →
Consents → Done → Account.

| # | Shot | Step |
|---|---|---|
| 01 | `01-customer-code-entry.png` | Business code entry (6-digit cells) |
| 02 | `02-code-filled.png` | Code 755862 entered |
| 03 | `03-business-resolved.png` | Business resolved: "Your electrician — Shand 1 Electrical" |
| 04 | `04-step01-postcode.png` | Step 1: postcode (local regex check only — **no address-lookup API call in the app flow**, despite the inventory listing one) |
| 05 | `05-step01-postcode-filled.png` | Postcode filled (LS1 4DY) |
| 06 | `06-step02-contact.png` | Step 2: contact details |
| 07 | `07-step02-contact-filled.png` | Contact filled |
| 08 | `08-step03-property-top.png` | Step 3: property profile (type/age/tenure) |
| 09 | `09-step03-property-bottom.png` | Property lower half (parking, fuse board, known issues) |
| 10 | `10-step04-job-type.png` | Step 4: job type — **options come from the tenant's services list** (Shand 1 offers EV charger / Consumer unit / Full rewire / Something else — no EICR) |
| 11 | `11-step04-job-type-selected.png` | Consumer unit selected |
| 12 | `12-step05-questionnaire-consumer-unit.png` | Step 5: consumer-unit questionnaire (variant 1) with live "Detail completeness" meter |
| 13 | `13-step05-questionnaire-answers.png` | Questionnaire answers (survey recommendation, repeated tripping, no RCD) |
| 14 | `14-step05-questionnaire-bottom.png` | Questionnaire lower half |
| 15 | `15-step06-photos-permission-denied.png` | Step 6: photos — "Photo library access denied" on this rig (see notes). Continue is NOT blocked even though the banner says "Consumer unit photo required" |
| 16 | `16-step07-timing.png` | Step 7: urgency + preferred dates |
| 17 | `17-step07-timing-selected.png` | "This week" selected |
| 18 | `18-step08-budget.png` | Step 8: budget & context |
| 19 | `19-step08-budget-selected.png` | £500–£1,000 selected |
| 20 | `20-step09-consents.png` | Step 9: consents |
| 21 | `21-step09-consents-ticked.png` | Required consents ticked |
| 22 | `22-step10-confirmation.png` | Step 10: **"Shand 1 Electrical has your request"** + summary + "Create account to track your quote" — shown even though nothing was created (QE-M2-7) |
| 23 | `23-step11-account-blank.png` | Step 11 (Account) renders **blank** — `AccountCreationStep` returns null because `submittedAck` is null, i.e. the submission never produced an ack (QE-M2-7 consequence) |
| 24 | `24-retry-confirmation-same-result.png` | Second full run (different email) — same outcome |
| 25 | `25-variant-qe-tenant-job-types.png` | Variant run on the QE Wave2 tenant (code 618569): job-type list includes EICR |
| 26 | `26-variant-eicr-questionnaire.png` | EICR questionnaire (variant 2): report purpose, last EICR date, occupancy, circuit count, remedial works |

## QE-M2-7 (S1) — guest quote requests from the app never reach the backend

Evidence:
- Two full drives (emails `qe-w2-cust-…@example.com`, `qe-w2-cust2-…@example.com`)
  both ended at the confirmation screen (shots 22/24).
- `GET /quote-requests` as the trade user immediately after each run shows no new
  request; the account step rendered blank both times (`submittedAck` null).
- The same endpoint works fine from curl: three manual probes with the same payload
  shape returned 201 and appeared in the trade list (auto-converted by the quote
  automation). So the server side and payload shape are fine.
- Root cause (by inspection): `CustomerQuoteRequestFlow.submitToBackend` wraps the
  submit in `catch {}` ("capture UX should not hard-fail on a flaky submit") and
  always advances to the confirmation screen, so ANY failure is invisible. What
  actually fails client-side could not be observed from the device (no request
  reached the API logs for either drive; a 422 logged at 01:43:52 UTC on this
  endpoint could not be attributed — a second agent was driving the same account).
- Impact: a real customer would believe their request was sent; the electrician
  never sees it. The web portal intake (E5) works — this is app-specific.

## Notes

- Photo capture was not drivable on this rig: the app showed "Photo library access
  denied" without presenting the system prompt (TCC row was `denied` before any
  prompt; flipping it via simctl/sqlite requires an app restart, which loses the
  in-memory flow). No photo was attached; confirmation summary shows
  "Photos / videos: 0". On a real device the permission prompt would appear.
- The media step's "required" label is advisory only (Continue enabled with zero
  photos).
- "1 quote generating" seen on the customer home (E1 shot 04) suggests the
  automation drafted a quote for the web wave's request — not from this flow.

# My Trade Portal — Marketing Video Package (for 11labs)

## What this is

Raw screen recordings of the real iOS app running against the production
backend, one clip per feature. Scripted, typo-free demo flows with realistic
data. 9:16 (1170×2532 @30fps, H.264) — shot on an iOS simulator build that is
pixel-identical to the App Store/TestFlight build. Reformat freely to 16:9 for
website hero use.

Every person, business, phone number and email in the footage is **fictional**:
phone numbers use the Ofcom drama range (07700 900xxx) and emails use reserved
example.com addresses. Safe to publish as-is.

## Brand

- **Product name:** My Trade Portal
- **One-liner (proposed):** "Quotes to invoices in minutes — powered by AI."
  (alternatives: "Less admin. More sparks." / "The AI back office for trades.")
- **Primary colour:** `#2563EB` (blue) — in-app default
- **Secondary/accent:** `#F59E0B` (amber), success `#10B981` (green)
- **Demo tenant brand (shown in footage):** Hartley Electrical Services Ltd —
  primary `#1D4ED8`, secondary `#F59E0B`
- **Typeface:** system SF Pro (iOS system font — use SF Pro or Inter in overlays)
- **Logo/assets:** see `assets/` — `mtp-app-icon.png` (app icon, blue),
  `mtp-logo-icon.jpg` (product logo mark, orange bolt)

## Cast (fictional)

| Role | Name | Details shown in-app |
|---|---|---|
| Electrician (tenant owner) | Tom Hartley | Hartley Electrical Services Ltd, Harrogate, 07700 900123, NICEIC |
| Customer | Sarah Thompson | 27 Dene Road, Harrogate HG2 8JR, 07700 900231 |
| Customer | David Whitfield | 4 Crag Lane, Harrogate HG3 1PR — EV charger job |
| Customer | Priya Patel | 8 Victoria Avenue, Harrogate HG1 5RD — consumer unit quote |
| Customer | Margaret Ellis | 19 Hookstone Drive, Harrogate — garden lighting |
| Customer | Helen Carter | new-quote intake demo |
| Customer | Martin Fisher | garden-office power intake demo |

## Clips

| File | Duration | Feature | Content |
|---|---|---|---|
| `01-ai-quote-drafting.mp4` | ~3.5 min (trim generation) | AI quote drafting | Trade intake: name + plain-English job description typed live → "Generate AI quote" → Quotes list "generating" banner → "Your AI quote is ready" → review screen with AI-confidence %, assumptions panel, priced line items, VAT totals |
| `02-customer-quote-request.mp4` | ~4 min | Customer quote request | Logged-in customer runs the 10-step request wizard (postcode, contact prefs, property profile, category, live-typed description, urgency) → confirmation "Hartley Electrical has your request" → AI chat opens → AI follow-up message → customer reply sent |
| `03-review-and-send.mp4` | ~16 s | Review & approval | Quotes list → AI-drafted quote (backend AI triage has already auto-drafted it from the customer request) → review (confidence, assumptions, editable lines, VAT totals) → "Send quote" → Quotes list with Sent badge |
| `04-job-management.mp4` | ~16 s | Job booking & management | Accepted quote → "Convert to job" → Job detail (CONFIRMED badge, customer card, address, schedule) → Calendar tab with bookings |
| `05-one-touch-invoice.mp4` | ~53 s | One-touch invoicing | Today's job opened → Start job (IN PROGRESS) → Mark complete (COMPLETED) → invoice line typed → "Create & send invoice · £1,240.00" → Invoice detail (SENT badge, totals, line items) → Mark as paid → "Payment received" banner |
| `06-dashboard-overview.mp4` | ~18 s | Dashboard & analytics | Dashboard: Active leads + Outstanding quotes stat cards, Top leads, calendar strip → notifications bell → notifications list → settings peek |

## Notes for the edit

- Generation steps are real LLM calls: clip 01 contains a long "generating"
  stretch (LLM drafting, typically 2–5 min real time) — cut or time-lapse at
  will; the ready-banner moment is the payoff beat. Clip 03 starts after the
  backend AI triage has already drafted the quote, so no generation wait is
  shown there.
- Keystrokes in text fields are real-time (no fast-forward needed).
- The AI chat follow-up in clip 02 arrives ~5–15s after the chat opens.
- No audio in any clip.
- Dark mode is not in this build; footage is light UI only.

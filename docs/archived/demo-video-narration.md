# Demo video narration script

## Marketing cut — `marketing-journey.mp4` (single, ~168s, no captions)

Clean iPhone-resolution screen recording of the real app, one continuous story
across both profiles — now including the **voice-to-quote / voice-to-cert** and
**offline-first** showcases. No burned-in captions — record the voiceover
against these approximate beat timings.

| Time | Beat | Suggested narration |
|---|---|---|
| 0:00 | Customer opens the app, enters a 6-digit code | "Homeowners find their local electrician with a simple 6-digit code…" |
| 0:04 | Requests a quote; confirms postcode | "…and request a quote in minutes." |
| 0:06 | Contact details — In-app Chat | "They choose how they'd like to be contacted — including in-app chat." |
| 0:09 | Property profile | "A few structured questions capture the property…" |
| 0:11 | Job type + questionnaire | "…and the exact job." |
| 0:15 | Fuse-board photo | "They add a photo of the fuse board." |
| 0:17 | Urgency, budget, consent, submit | "Then submit — no endless forms." |
| 0:22 | Confirmation | "The business will review and send the quote." |
| 0:24 | AI assistant follows up in chat | "An AI assistant follows up in chat to refine the quote…" |
| 0:26 | 5-question Q&A | "…so it's accurate before a human touches it." |
| 0:42 | Electrician logs in | "Meanwhile the electrician opens their mobile back office." |
| 0:46 | **Goes offline (on-site, no signal)** | "Out in a basement with no signal? No problem — the app works fully offline." |
| 0:48 | **Dictates a quote by voice** (waveform + live transcript) | "They just describe the job out loud…" |
| 1:05 | **AI extracts the line items** (saved on device) | "…and AI turns it into a priced quote — saved on the device." |
| 1:09 | **Dictates an EICR by voice** | "Same for certificates: dictate the test results…" |
| ~1:20 | **BS 7671 validation** (per-circuit PASS, Satisfactory) | "…and the app validates every Zs, RCD and IR reading against BS 7671, then issues the EICR." |
| 1:40 | **Back online — everything syncs** | "Back in signal, everything syncs automatically — nothing is ever lost." |
| 1:45 | Opens the new customer lead | "Back to the lead that came in from the customer app…" |
| 1:49 | Generates the AI quote | "…AI drafts the quote…" |
| 1:54 | Reviews the draft (78% confidence) | "They review every line…" |
| 1:58 | Switches pricing model | "…switch between time-and-materials and per-point pricing…" |
| 2:02 | Approves & sends | "…and send — humans always have the final say." |
| 2:04 | Customer returns; quote received | "The customer gets the quote…" |
| 2:12 | Reviews line items & assumptions | "…fully transparent." |
| 2:16 | Accepts the quote | "They accept…" |
| 2:18 | Picks a day/time, confirms booking | "…and book straight from the app." |
| 2:21 | Electrician, job day — dashboard | "On the day, the job's on the calendar." |
| 2:25 | Opens the job | "They open the job…" |
| 2:29 | Navigate to site | "…and navigate to site." |
| 2:32 | Start + complete | "Once done…" |
| 2:35 | Completion notes + on-site variation | "…they log completion notes and add on-site variations." |
| 2:38 | Create & send invoice | "The invoice is created and sent in seconds…" |
| 2:41 | Payment received | "…payment comes in…" |
| 2:44 | Revenue dashboard | "…and the business sees its revenue and profit at a glance." |

---

## Framed cuts (with burned-in captions)

Voiceover script for the two automated marketing walkthroughs produced by
`services/pwa/scripts/build-demo-videos.sh`. Timestamps are for the **final
MP4s**, which prepend a 3-second intro card, so the in-app action starts at
`0:03`. The on-screen captions are burned in automatically and timed live
during recording; this script is the spoken narration to record over the top.

- Format: 1080×1920 (9:16), H.264, silent audio track.
- Electrician video: ~55s. Customer video: ~72s.
- Tone: confident, plain-English, UK trades audience. No hype.

---

## Video 1 — The Electrician's Journey (`electrician-journey.mp4`)

> Hook: an electrician runs their whole back office from a phone.

| Final time | On-screen | Narration |
|---|---|---|
| 0:00–0:03 | Intro card | — |
| 0:03–0:06 | Entry screen | "My Trade Portal is the white-label app that lets any UK electrician run their business from their phone." |
| 0:06–0:10 | Trade login | "They log in to their own branded back office." |
| 0:10–0:14 | Dashboard | "Every morning opens on the hottest leads and today's calendar — one tap to act." |
| 0:14–0:17 | Lead detail | "They open a lead and see the customer, the photos and the notes." |
| 0:17–0:21 | Quote intake | "The AI scopes the job from the customer's answers…" |
| 0:21–0:25 | Intake details | "…a few taps confirm the site details…" |
| 0:25–0:28 | Draft appears | "…and it drafts a full quote in seconds." |
| 0:28–0:32 | Quote line items | "The electrician reviews the line items, the VAT and the total." |
| 0:32–0:36 | Pricing toggle | "They can switch between time-and-materials and fixed per-point pricing." |
| 0:36–0:40 | Approve | "AI drafts, but humans approve — the electrician always has the final say." |
| 0:40–0:43 | Calendar | "Once approved, the job lands on the calendar…" |
| 0:43–0:49 | Job detail | "…with navigate, call and assign, all from their pocket." |
| 0:49–0:55 | Outro card | "My Trade Portal — your electrical business, in your pocket." |

---

## Video 2 — The Customer's Journey (`customer-journey.mp4`)

> Hook: a homeowner gets a trusted quote and books the work, all in the app.

| Final time | On-screen | Narration |
|---|---|---|
| 0:00–0:03 | Intro card | — |
| 0:03–0:07 | Enter code | "Homeowners find their local electrician by entering a simple 6-digit code." |
| 0:07–0:10 | Branded landing | "The app instantly becomes that electrician's branded portal." |
| 0:10–0:13 | Start request | "They request a quote in under three minutes." |
| 0:13–0:17 | Postcode | "We check the postcode is inside the service area…" |
| 0:17–0:20 | Contact | "…take a few contact details…" |
| 0:20–0:23 | Property | "…and capture the property, because its age drives an accurate quote." |
| 0:23–0:27 | Job type | "They pick the job — the tiles only show what this electrician offers." |
| 0:27–0:30 | Questionnaire | "A short, structured questionnaire replaces vague free text." |
| 0:30–0:33 | Photos | "They add photos of the fuse board with a guided overlay." |
| 0:33–0:36 | Urgency & triage | "If it's an emergency, we route straight to a callback instead of a quote." |
| 0:36–0:39 | Budget | "Optional budget context helps the electrician pitch it right." |
| 0:39–0:43 | Consent & submit | "They give consent and submit." |
| 0:43–0:46 | Confirmation | "No false promises — the business reviews and sends the quote." |
| 0:46–0:50 | Customer portal | "Everything is tracked in their branded customer portal." |
| 0:50–0:54 | Quote detail | "They open the quote — every line item and assumption is transparent." |
| 0:54–0:57 | Accept | "They accept with one tap…" |
| 0:57–1:01 | Book date | "…pick a day and time…" |
| 1:01–1:06 | Confirm / outro | "…and the booking lands on both calendars instantly." |

---

## Regenerating

```bash
# Both videos + posters (starts the Expo web server if needed):
services/pwa/scripts/build-demo-videos.sh all

# One journey only:
services/pwa/scripts/build-demo-videos.sh electrician
```

The captions are re-timed on every run, so if you change the pacing in
`services/pwa/scripts/demo/journeys.js` the burned-in captions stay in sync.
Re-record the narration against the new timings if you change scene order.

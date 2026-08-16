# Demo video narration script

## Marketing cut — `marketing-journey.mp4` (single, ~112s, no captions)

Clean iPhone-resolution screen recording of the real app, one continuous story
across both profiles. No burned-in captions — record the voiceover against these
approximate beat timings. Times are from the app content (the file has no
intro/outro cards).

| Time | Beat | Suggested narration |
|---|---|---|
| 0:00 | Customer opens the app, enters a 6-digit code | "Homeowners find their local electrician with a simple 6-digit code…" |
| 0:07 | Requests a quote; confirms postcode | "…and request a quote in minutes." |
| 0:09 | Contact details — In-app Chat | "They choose how they'd like to be contacted — including in-app chat." |
| 0:12 | Property profile | "A few structured questions capture the property…" |
| 0:14 | Job type + questionnaire | "…and the exact job." |
| 0:18 | Fuse-board photo | "They add a photo of the fuse board." |
| 0:19 | Urgency, budget, consent, submit | "Then submit — no endless forms." |
| 0:25 | Confirmation | "Honest expectations: the business will review and send the quote." |
| 0:27 | AI assistant follows up in chat | "An AI assistant follows up in chat to fill any gaps…" |
| 0:29 | 5-question Q&A refines the quote | "…so the quote is accurate before a human ever touches it." |
| 0:45 | Electrician logs in; new-lead notification | "The electrician gets the lead on their phone." |
| 0:49 | Opens lead + customer's photo | "They review the details and the customer's photo…" |
| 0:54 | Generates the AI quote | "…and AI drafts the quote." |
| 0:59 | Reviews the draft (78% confidence) | "They review every line…" |
| 1:03 | Switches pricing model | "…switch between time-and-materials and per-point pricing…" |
| 1:07 | Approves & sends | "…and send — humans always have the final say." |
| 1:09 | Customer returns; quote received | "The customer gets the quote…" |
| 1:16 | Reviews line items & assumptions | "…fully transparent." |
| 1:20 | Accepts the quote | "They accept…" |
| 1:22 | Picks a day/time, confirms booking | "…and book straight from the app." |
| 1:26 | Electrician, job day — dashboard | "On the day, the job's on the calendar." |
| 1:30 | Opens the job | "They open the job…" |
| 1:33 | Navigate to site | "…and navigate to site." |
| 1:36 | Start + complete | "Once done…" |
| 1:39 | Completion notes + on-site variation | "…they log completion notes and add on-site variations." |
| 1:43 | Create & send invoice | "The invoice is created and sent in seconds…" |
| 1:45 | Payment received | "…payment comes in…" |
| 1:48 | Revenue dashboard | "…and the business sees its revenue and profit at a glance." |

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

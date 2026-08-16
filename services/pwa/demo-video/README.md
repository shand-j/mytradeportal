# Demo videos

Walkthrough videos of the interactive mock iOS app, generated automatically from
the live Expo web build — no manual screen recording or editing.

## Primary: marketing cut (single, clean, no captions/frame)

`marketing-journey.mp4` — one continuous ~112s story at iPhone resolution
(1170×2532, portrait), **no phone frame, no captions, no background** — a clean
base cut for a human editor to add voiceover/music.

Storyboard (one story, both profiles):
1. Customer finds the electrician (6-digit code) and requests a quote — full
   structured journey to submission (In-app Chat contact, property, job type,
   photo, urgency, budget, consent).
2. The AI assistant follows up in chat and refines the quote (Q&A), then confirms
   the quote is under way.
3. Electrician: new-lead notification → review lead + customer photo → AI-drafted
   quote (78% confidence) → pricing toggle → approve & send.
4. Customer: quote received → review line items/assumptions → accept → book a date.
5. Electrician (job day): dashboard today → job detail → navigate → start/complete
   → completion notes → on-site variation → create & send invoice → payment
   received → revenue dashboard.

Regenerate (Expo web must be running on :8085):

```bash
cd services/pwa && npx expo start --web --port 8085 --clear    # terminal 1
node services/pwa/scripts/record-marketing-video.js            # terminal 2
```

Beat-by-beat notes for voiceover are in
[`docs/demo-video-narration.md`](../../../docs/demo-video-narration.md).

## Alternate: framed, captioned per-journey cuts

Two shorter cuts with a drawn iPhone frame, burned-in captions and branded
intro/outro cards (useful for social / auto-captioned contexts).

| File | Journey | Length |
|---|---|---|
| `electrician-journey.mp4` | Log in → review AI draft quote → approve → schedule | ~55s |
| `customer-journey.mp4` | Enter code → request quote → accept → book a date | ~72s |
| `*-journey-poster.jpg` | Poster stills for thumbnails / decks | — |

Format: 1080×1920 (9:16), H.264, silent audio track, drawn iPhone frame with
burned-in captions and branded intro/outro cards.

## Regenerate (framed cuts)

```bash
# From the repo root — starts the Expo web server on :8084 if needed.
services/pwa/scripts/build-demo-videos.sh all
```

Individual steps (Expo web must be running on `:8084`):

```bash
# 1. Record raw screen capture + live-timed captions
node services/pwa/scripts/record-demo-video.js --journey=electrician

# 2. Composite frame + captions + intro/outro into the final MP4
python services/pwa/scripts/compose_demo_video.py --journey electrician
```

## How it works

- `scripts/demo/journeys.js` — the two journeys as ordered, captioned scenes
  driven through the real UI via Playwright. Shared with screenshot capture.
- `scripts/record-demo-video.js` — records the viewport with Playwright and
  writes `raw/<journey>.webm` plus `raw/<journey>.captions.json` (captions are
  timed live so they always match the on-screen action).
- `scripts/compose_demo_video.py` — Pillow draws the phone frame, caption bars
  and intro/outro cards; ffmpeg composites and encodes the final MP4 + poster.

## What is committed vs generated

- Committed: the final `*.mp4` and `*-poster.jpg` deliverables.
- Generated (git-ignored): `raw/` recordings and `assets/` intermediate PNGs.
  Recreate them any time with the commands above.

The spoken narration script lives in
[`docs/demo-video-narration.md`](../../../docs/demo-video-narration.md).

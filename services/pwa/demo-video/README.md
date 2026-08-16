# Demo videos

Marketing-ready walkthrough videos of the interactive mock iOS app, showing the
two core journeys end to end. These are generated automatically from the live
Expo web build — no manual screen recording or editing.

| File | Journey | Length |
|---|---|---|
| `electrician-journey.mp4` | Log in → review AI draft quote → approve → schedule | ~55s |
| `customer-journey.mp4` | Enter code → request quote → accept → book a date | ~72s |
| `*-journey-poster.jpg` | Poster stills for thumbnails / decks | — |

Format: 1080×1920 (9:16), H.264, silent audio track, drawn iPhone frame with
burned-in captions and branded intro/outro cards.

## Regenerate

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

# Demo media slots

The landing page is wired for video; drop files here to activate each slot.
Missing files degrade gracefully to the poster frame (a real app screenshot),
so the page is presentable before the final renders arrive.

## Hero

- `hero.mp4` — hero demo video (AI-generated iPhone render walkthrough or the
  11labs edit of clip 01). Portrait 9:19.5, muted/autoplay/loop in-page.

## Feature clips (one per features section, in order)

- `feature-quotes.mp4` — clip 01 (AI quote drafting)
- `feature-intake.mp4` — clip 02 (customer quote request)
- `feature-jobs.mp4` — clip 04 (job management)
- `feature-invoices.mp4` — clip 05 (one-touch invoicing)

## Posters

`posters/*.jpg` are real screenshots extracted from the screen recordings.
Replace with AI-render frames when the renders arrive — to composite a render
*with* the video playing on its screen, pass `frameSrc` + `screenInset` to
`<MediaSlot>` (see `components/media-slot.tsx`).

Keep mp4s out of git (they are large) — deploy them with the hosting
platform's asset storage or a CDN and reference absolute URLs in the
components instead.

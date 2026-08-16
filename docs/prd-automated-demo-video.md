# PRD 5 — Automated Demo Video

> Scope: produce a repeatable, automated marketing video of the Milestone 1 interactive mock. The video must look like a fully built product with a real backend.

## 1. Goal

Create an automated pipeline that records a scripted walkthrough of the white-label iOS electrician app and stitches it into a 90–120 second marketing video with a phone frame overlay, captions, and intro/outro cards. The same script also regenerates the screenshot set used on landing pages and in investor decks.

## 2. Approach

### Primary: Playwright browser recording + post-processing

- Run the interactive mock in **web mode** at a fixed iPhone 14/15 viewport (390×844) using `npx expo start --web --port 8084`.
- Drive the UI with Playwright (`chromium`) and the same `capture-demo-screenshots.js` flow.
- Use Playwright’s built-in `recordVideo` to capture the viewport directly to a WebM/MP4 during the run.
- Post-process with `ffmpeg`:
  - Scale the viewport to 1080×1920 or 1170×2532.
  - Overlay a static iPhone 15 frame PNG with a transparent screen area.
  - Add captions/subtitles as burn-in text at the bottom of the phone screen.
  - Add an intro card (3s) and outro card (3s) with the logo + tagline.
- Export to MP4 (H.264) for web/social.

### Fallback: iOS Simulator recording

- Reserved for Beta when the demo relies on native-only flows (camera, Share Extension, Apple Maps).
- For Milestone 1, the web recording is sufficient and far more reliable.

## 3. Storyboard & narration

The video tells a single story: a homeowner requests a quote, the electrician reviews the AI draft and sends it, the homeowner accepts and books a date.

| Scene | Route / testID | Action | On-screen text | Narration (draft) | Duration |
|---|---|---|---|---|---|
| 0. Intro card | — | Logo + tagline | “My Trade Portal — run your electrical business from your phone.” | — | 3s |
| 1. Entry screen | `/` | Show entry | “One app, white-labelled for every electrician.” | “My Trade Portal is the white-label app that lets electricians run their entire business from their phone.” | 4s |
| 2. Customer enters code | `entry-find-business` | Type 123456 | “Find your electrician.” | “Homeowners find their local electrician by entering a simple 6-digit code.” | 4s |
| 3. Branded landing | business landing | Show branded page | “Your branded customer portal.” | “The app instantly becomes their branded portal.” | 3s |
| 4. Customer request quote | request quote | Tap, show C1/C3 | “Request a quote in under 3 minutes.” | “They request a quote, answer a few structured questions, and even upload a photo of their fuse board.” | 8s |
| 5. Electrician login | trade-login | Type credentials | “Electrician login.” | “Meanwhile, the electrician logs in to their mobile back office.” | 4s |
| 6. Dashboard | `/dashboard` | Show dashboard | “Every morning starts with action.” | “The dashboard shows the hottest leads and today’s calendar — one tap to act.” | 5s |
| 7. Lead detail | lead detail | Tap lead card | “Lead detail.” | “They review the lead, the customer details, and the photos.” | 4s |
| 8. Generate AI quote | generate quote | Tap, show intake | “AI drafts the quote.” | “AI scopes the job and drafts a quote in seconds.” | 5s |
| 9. Quote edit | quote edit | Show line items, toggle per-point | “Review, switch pricing, approve.” | “The electrician reviews the line items, switches between time-and-materials and per-point pricing, and approves the quote.” | 8s |
| 10. Customer accepts | customer quote detail | Accept + book date | “Customer accepts and books.” | “The homeowner accepts the quote and books a date straight from the app.” | 6s |
| 11. Calendar | calendar | Show booking | “Calendar updated.” | “The job lands on the calendar with navigation and contact actions.” | 4s |
| 12. Settings / branding | settings / branding | Show settings menu | “White-label, settings, done.” | “Everything is white-labelled, settings are reachable but never in the way.” | 4s |
| 13. Outro card | — | Logo + CTA | “Get your first lead this week.” | “My Trade Portal — your electrical business, in your pocket.” | 3s |

**Total target:** ~60–75 seconds for the app walkthrough + 6s intro/outro = ~70–80s. Social cut can be 30s by removing settings and C1 details.

## 4. Tools & assets

| Tool | Purpose |
|---|---|
| Playwright | Drive the mock and capture viewport video |
| `ffmpeg` | Composite frame, captions, intro/outro, encode MP4 |
| Static PNG | iPhone 15 frame with transparent screen (1200×2600, 75px bezels) |
| `docs/demo-video-narration.md` | Final voiceover script, synced to scene timestamps |
| `services/pwa/scripts/record-demo-video.js` | The main automation script |

## 5. Script: `record-demo-video.js`

The script should:
1. Start the browser with viewport 390×844 and `recordVideo` enabled.
2. Navigate to the Expo web dev server URL.
3. Execute the same interactions as `capture-demo-screenshots.js` plus the customer accept/book scenes.
4. At the end of the run, close the browser and receive the WebM video file from Playwright.
5. Call `ffmpeg` to:
   - Pad/scale the WebM to fit the iPhone frame transparent area.
   - Add the phone frame overlay.
   - Add intro/outro cards.
   - Burn captions from a JSON file `demo-video-captions.json`.
6. Output to `services/pwa/demo-video/demo-video.mp4`.

## 6. Captions format

`services/pwa/demo-video/captions.json`:
```json
[
  { "start": 3.0, "end": 6.0, "text": "One app, white-labelled for every electrician." },
  { "start": 7.0, "end": 11.0, "text": "Homeowners find their electrician with a 6-digit code." }
]
```

`ffmpeg` will draw these with `drawtext` at the bottom of the phone screen area.

## 7. Screenshot generation

`capture-demo-screenshots.js` should remain the primary screenshot pipeline. It can be run independently of the video script. Both scripts share the same `tapByText`, `tapTestId`, `typeCode`, etc. helpers.

The screenshot set for marketing should include at least:
1. entry
2. business-selected
3. trade-login
4. dashboard
5. lead-detail
6. quote-intake
7. quote-edit (time & materials)
8. quote-edit-per-point
9. request-info-chat
10. quotes
11. customers
12. customer-detail
13. calendar-day
14. calendar-week
15. settings
16. customer-login
17. customer-quotes
18. customer-quote-detail
19. customer-book-date
20. customer-profile

## 8. Success criteria

- A single command regenerates the full video and screenshot set.
- The final MP4 is 60–120 seconds, 1080p or better, and suitable for a website hero or investor pitch.
- The video clearly shows the white-label entry, AI quote draft, pricing toggle, customer accept/book, and calendar update.
- No manual editing is required for a “good enough” marketing cut.

## 9. Out of scope for Milestone 1

- Professional voiceover recording (script is provided; voiceover can be added later).
- Music or sound effects (post-processing can add these).
- Native iOS screen recording with device frame (future Beta/MVP cut).
- Automated upload to hosting/social platforms.

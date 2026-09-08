#!/usr/bin/env node
/**
 * Records the single, comprehensive marketing walkthrough of the app and
 * outputs a clean iPhone-resolution MP4 — no phone frame, no captions, no
 * background. This is the base cut for a human editor to add voiceover/music.
 *
 * Storyboard (one continuous story):
 *   Customer: find electrician -> request a quote (full journey) -> submit
 *   Customer: AI assistant follows up in chat to refine the quote
 *   Electrician: new-lead notification -> review lead + photo -> AI draft quote
 *              -> quick edits -> approve & send
 *   Customer: quote received -> review -> accept -> book a date
 *   Electrician (job day): dashboard today -> job detail -> navigate
 *              -> complete -> completion notes -> on-site variation
 *              -> create & send invoice -> payment received -> revenue dashboard
 *
 * Prerequisite: Expo web dev server running (default http://localhost:8085).
 *   cd mobile && npx expo start --web --port 8085
 *
 * Usage:
 *   node mobile/scripts/record-marketing-video.js
 *
 * Output: mobile/demo-video/marketing-journey.mp4 (+ poster)
 */
const { chromium } = require("playwright");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const { makeHelpers, sleep } = require("./demo/journeys");

const BASE_URL = process.env.DEMO_BASE_URL || "http://localhost:8085";
const RAW_DIR = path.resolve(__dirname, "..", "demo-video", "raw");
const OUT_DIR = path.resolve(__dirname, "..", "demo-video");
const VIEWPORT = { width: 390, height: 844 };

async function main() {
  fs.mkdirSync(RAW_DIR, { recursive: true });
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: 3,
    recordVideo: { dir: RAW_DIR },
  });
  const page = await context.newPage();
  const h = makeHelpers(BASE_URL);

  // Extra helpers layered on the shared ones.
  const scrollDown = async (dy = 500) => {
    await page.mouse.move(VIEWPORT.width / 2, VIEWPORT.height / 2);
    await page.mouse.wheel(0, dy);
    await sleep(700);
  };
  const scrollUp = async (dy = 900) => {
    await page.mouse.move(VIEWPORT.width / 2, VIEWPORT.height / 2);
    await page.mouse.wheel(0, -dy);
    await sleep(500);
  };
  const enterBusiness = async () => {
    await h.waitText(page, "My Trade Portal");
    await sleep(500);
    await h.typeCode(page, "123456");
    await h.tap(page, "entry-find-business", 700);
    await h.waitText(page, "Request a quote");
  };
  const log = (m) => console.log(`  ${((Date.now() - t0) / 1000).toFixed(1)}s  ${m}`);

  const t0 = Date.now();

  // ------------------------------------------------------------------
  // 1. Customer finds the electrician and starts a quote request.
  // ------------------------------------------------------------------
  log("Customer: open app + enter electrician code");
  await page.goto(BASE_URL, { waitUntil: "networkidle" });
  await enterBusiness();
  await sleep(1200);

  log("Customer: request a quote");
  await h.tap(page, "entry-request-quote", 700);
  await h.waitText(page, "check we cover your area");
  await sleep(700);
  await h.tap(page, "quote-check-area", 700);

  log("Customer: contact details (Online chat)");
  await sleep(500);
  await h.tapText(page, "Online chat", 500);
  await sleep(600);
  await h.tap(page, "quote-contact-continue", 700);

  log("Customer: property profile");
  await sleep(700);
  await scrollDown(360);
  await h.tap(page, "quote-property-continue", 700);

  log("Customer: choose job type");
  await h.tap(page, "quote-category-consumer_unit", 500);
  await sleep(500);
  await h.tap(page, "quote-category-continue", 700);

  log("Customer: job questionnaire");
  await sleep(900);
  await scrollDown(300);
  await h.tap(page, "quote-consumer-unit-continue", 700);

  log("Customer: add fuse-board photo");
  await sleep(800);
  await h.tap(page, "quote-media-continue", 700);

  log("Customer: timing & urgency");
  await sleep(800);
  await h.tap(page, "quote-urgency-continue", 700);

  log("Customer: budget");
  await sleep(600);
  await h.tap(page, "quote-budget-continue", 700);

  log("Customer: consent + submit");
  await sleep(500);
  await h.tap(page, "quote-consent-terms", 300);
  await h.tap(page, "quote-consent-contact", 300);
  await sleep(400);
  await h.tap(page, "quote-submit", 900);

  log("Customer: confirmation");
  await h.waitText(page, "has your request");
  await sleep(1600);
  await h.tap(page, "quote-done", 900);

  // ------------------------------------------------------------------
  // 2. AI assistant follows up in chat to refine the quote.
  // ------------------------------------------------------------------
  log("Customer: AI assistant notification");
  await h.waitText(page, "My quotes");
  await sleep(1200);
  await h.tap(page, "customer-ai-banner", 800);

  log("Customer: chat with AI assistant");
  // Answer each follow-up question by tapping the first suggested reply.
  for (let i = 0; i < 5; i++) {
    const chip = page.locator('[data-testid="chat-quick-reply-0"]').first();
    await chip.waitFor({ state: "visible", timeout: 15000 });
    await sleep(900);
    await chip.click({ force: true });
    await sleep(1500);
  }
  await h.waitText(page, "preparing your quote now");
  await sleep(2000);

  // ------------------------------------------------------------------
  // 3. Electrician: new lead -> AI draft quote -> edit -> send.
  // ------------------------------------------------------------------
  log("Electrician: log in");
  await page.goto(BASE_URL, { waitUntil: "networkidle" });
  await h.waitText(page, "My Trade Portal");
  await sleep(600);
  await h.tap(page, "entry-trade-login", 600);
  await h.waitText(page, "Electrician login");
  await sleep(500);
  await h.tapText(page, "Sign in", 800);
  await h.waitText(page, "New lead");
  await sleep(1200);

  // ------------------------------------------------------------------
  // Offline-first showcase.
  // ------------------------------------------------------------------
  log("Electrician: go offline (on-site, no signal)");
  await h.tap(page, "offline-toggle", 1400);
  await sleep(1500); // offline banner

  log("Electrician: back online — everything syncs");
  await h.tap(page, "offline-toggle", 1500); // "syncing" banner
  await sleep(3400); // "all changes synced" banner

  log("Electrician: open new lead");
  await h.tap(page, "dashboard-new-lead-banner", 800);
  await h.waitText(page, "Lead detail");
  await sleep(1000);
  await scrollDown(360); // reveal the customer's uploaded photo
  await sleep(1400);
  await scrollUp(200);

  log("Electrician: generate AI quote");
  await h.tapText(page, "Generate AI quote", 700);
  await h.waitText(page, "Quote intake");
  await sleep(700);
  await h.tap(page, "intake-property-type-house");
  await h.tap(page, "intake-bedrooms-3");
  await h.tap(page, "intake-cu-location-hallway");
  await h.fillPlaceholder(page, "Driveway parking", "Driveway parking, key-safe 1234");
  await h.fillPlaceholder(page, "Any access restrictions", "Dog on site, board in garage");
  await sleep(600);
  await h.tap(page, "intake-generate-quote", 900);

  log("Electrician: review AI draft quote");
  await h.waitText(page, "Review AI quote");
  await sleep(1600);
  await scrollDown(280);
  await sleep(900);
  await scrollUp(280);

  log("Electrician: switch pricing model");
  await h.tap(page, "pricing-per_point", 1200);
  await sleep(900);
  await h.tap(page, "pricing-time_materials", 1000);
  await sleep(700);

  log("Electrician: approve & send");
  await h.tapAnyText(page, /Approve & send|Update quote|Save changes/, 1400);
  await sleep(800);

  // ------------------------------------------------------------------
  // 4. Customer: quote received -> accept -> book a date.
  // ------------------------------------------------------------------
  log("Customer: return to accept the quote");
  await page.goto(BASE_URL, { waitUntil: "networkidle" });
  await enterBusiness();
  await sleep(700);
  await h.tap(page, "entry-customer-login", 600);
  await h.waitText(page, "Customer login");
  await sleep(500);
  await h.tapText(page, "Sign in", 900);
  await h.waitText(page, "My quotes");
  await sleep(1400);

  log("Customer: open received quote");
  await h.tap(page, "quote-card-q1", 900);
  await h.waitText(page, "Assumptions");
  await sleep(1600);
  await scrollDown(260);
  await sleep(700);
  await scrollUp(260);

  log("Customer: accept quote");
  await h.tapText(page, "Accept quote", 900);
  await h.waitText(page, "Book a date");
  await sleep(900);

  log("Customer: pick day + time, confirm booking");
  await h.tap(page, "book-day-1", 500);
  await h.tap(page, "book-time-1", 500);
  await sleep(700);
  await h.tapText(page, "Confirm booking", 1600);

  // ------------------------------------------------------------------
  // 5. Electrician (job day): navigate -> complete -> invoice -> paid -> revenue.
  // ------------------------------------------------------------------
  log("Electrician: job day, back to dashboard");
  await page.goto(BASE_URL, { waitUntil: "networkidle" });
  await h.waitText(page, "My Trade Portal");
  await sleep(600);
  await h.tap(page, "entry-trade-login", 600);
  await h.waitText(page, "Electrician login");
  await sleep(400);
  await h.tapText(page, "Sign in", 800);
  await h.waitText(page, "New lead");
  await sleep(900);

  log("Electrician: open today's job");
  await scrollDown(520); // down to the calendar / today's booking
  await sleep(600);
  await h.tap(page, "dashboard-job-j1", 900);
  await h.waitText(page, "Job detail");
  await sleep(1100);

  log("Electrician: navigate to site");
  await scrollDown(240);
  await sleep(500);
  await h.tap(page, "job-navigate", 1200);
  await sleep(700);

  log("Electrician: start + complete job");
  await scrollUp(600);
  await sleep(300);
  await h.tap(page, "job-start", 900);
  await h.tap(page, "job-complete", 1000);

  log("Electrician: completion notes + on-site variation");
  await scrollDown(520);
  await sleep(1200);
  await h.tap(page, "job-add-variation", 1000);
  await sleep(1000);

  log("Electrician: create & send invoice");
  await h.tap(page, "job-create-invoice", 1200);
  await h.waitText(page, "Payment method");
  await sleep(1400);

  log("Electrician: mark invoice paid");
  await h.tap(page, "invoice-mark-paid", 1200);
  await h.waitText(page, "Payment received");
  await sleep(1600);

  log("Electrician: revenue dashboard");
  await h.tap(page, "invoice-view-revenue", 1200);
  await h.waitText(page, "Revenue & costs");
  await sleep(2400);

  const video = page.video();
  await context.close();
  await browser.close();

  const rawPath = await video.path();
  const finalWebm = path.join(RAW_DIR, "marketing.webm");
  fs.renameSync(rawPath, finalWebm);
  const total = (Date.now() - t0) / 1000;
  console.log(`\nRecorded marketing walkthrough: ${total.toFixed(1)}s`);
  console.log(`  raw: ${finalWebm}`);

  // Transcode to a clean iPhone-portrait MP4 (no frame/captions), upscaled and
  // lightly sharpened for a crisp screen-recording look.
  const outMp4 = path.join(OUT_DIR, "marketing-journey.mp4");
  console.log("Transcoding to iPhone-resolution MP4…");
  const ff = spawnSync(
    "ffmpeg",
    [
      "-y",
      "-i",
      finalWebm,
      "-f",
      "lavfi",
      "-i",
      "anullsrc=r=44100:cl=stereo",
      "-vf",
      "scale=1170:2532:flags=lanczos,setsar=1,unsharp=5:5:0.7:5:5:0.0,fps=30,format=yuv420p",
      "-map",
      "0:v:0",
      "-map",
      "1:a:0",
      "-c:v",
      "libx264",
      "-preset",
      "medium",
      "-crf",
      "19",
      "-c:a",
      "aac",
      "-shortest",
      "-movflags",
      "+faststart",
      outMp4,
    ],
    { stdio: "inherit" }
  );
  if (ff.status !== 0) {
    // Fallback: video only (no silent audio track).
    spawnSync(
      "ffmpeg",
      [
        "-y",
        "-i",
        finalWebm,
        "-vf",
        "scale=1170:2532:flags=lanczos,setsar=1,unsharp=5:5:0.7:5:5:0.0,fps=30,format=yuv420p",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "19",
        "-movflags",
        "+faststart",
        outMp4,
      ],
      { stdio: "inherit" }
    );
  }

  // Poster still ~55% through.
  const poster = path.join(OUT_DIR, "marketing-journey-poster.jpg");
  spawnSync(
    "ffmpeg",
    [
      "-y",
      "-ss",
      `${(total * 0.55).toFixed(1)}`,
      "-i",
      outMp4,
      "-frames:v",
      "1",
      "-update",
      "1",
      "-q:v",
      "3",
      poster,
    ],
    { stdio: "inherit" }
  );

  console.log(`\nDone: ${outMp4}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

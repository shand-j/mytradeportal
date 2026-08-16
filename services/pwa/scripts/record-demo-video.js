#!/usr/bin/env node
/**
 * Records a marketing walkthrough video of one demo journey.
 *
 * Prerequisite: the Expo web dev server must be running, e.g.
 *   cd services/pwa && npx expo start --web --port 8084
 *
 * Usage:
 *   node services/pwa/scripts/record-demo-video.js --journey=electrician
 *   node services/pwa/scripts/record-demo-video.js --journey=customer
 *
 * Output (under services/pwa/demo-video/raw/):
 *   <journey>.webm            raw 1170x2532 screen recording
 *   <journey>.captions.json   caption text + start/end times (seconds)
 *
 * The raw recording is post-processed into a framed MP4 by
 * compose_demo_video.py. Captions are timed live during the run so they stay
 * in sync with the on-screen action regardless of machine speed.
 */
const { chromium } = require("playwright");
const fs = require("node:fs");
const path = require("node:path");
const { journeys, makeHelpers, sleep } = require("./demo/journeys");

const BASE_URL = process.env.DEMO_BASE_URL || "http://localhost:8084";
const OUT_DIR = path.resolve(__dirname, "..", "demo-video", "raw");

// iPhone-class logical viewport. Playwright records at the viewport size and the
// app fills the whole frame; we upscale into the phone frame during compositing.
// deviceScaleFactor 2 gives cleaner text anti-aliasing in the captured frames.
const VIEWPORT = { width: 390, height: 844 };

function parseArgs() {
  const arg = process.argv.find((a) => a.startsWith("--journey="));
  const journey = (arg ? arg.split("=")[1] : process.env.JOURNEY || "electrician").trim();
  if (!journeys[journey]) {
    console.error(`Unknown journey "${journey}". Options: ${Object.keys(journeys).join(", ")}`);
    process.exit(1);
  }
  return journey;
}

async function main() {
  const journeyKey = parseArgs();
  const journey = journeys[journeyKey];
  fs.mkdirSync(OUT_DIR, { recursive: true });

  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: 2,
    recordVideo: { dir: OUT_DIR },
  });
  const page = await context.newPage();
  const h = makeHelpers(BASE_URL);

  const captions = [];
  const t0 = Date.now();

  for (const scene of journey.scenes) {
    const start = (Date.now() - t0) / 1000;
    try {
      await scene.action(page, h);
    } catch (err) {
      console.error(`Scene failed: "${scene.caption}"`);
      throw err;
    }
    const elapsed = (Date.now() - t0) / 1000 - start;
    const minS = (scene.minMs || 0) / 1000;
    if (elapsed < minS) await sleep((minS - elapsed) * 1000);
    // Caption spans from when the scene started until the next scene starts.
    captions.push({ text: scene.caption, start: Number(start.toFixed(2)) });
    console.log(`  ${start.toFixed(1)}s  ${scene.caption}`);
  }

  // Small tail so the final scene isn't cut and the last caption can display.
  await sleep(1200);
  const totalDuration = (Date.now() - t0) / 1000;

  // Fill in caption end times.
  for (let i = 0; i < captions.length; i++) {
    captions[i].end =
      i < captions.length - 1
        ? captions[i + 1].start
        : Number(totalDuration.toFixed(2));
  }

  const video = page.video();
  await context.close(); // finalises the video file
  await browser.close();

  const rawPath = await video.path();
  const finalWebm = path.join(OUT_DIR, `${journeyKey}.webm`);
  fs.renameSync(rawPath, finalWebm);

  const captionsPath = path.join(OUT_DIR, `${journeyKey}.captions.json`);
  fs.writeFileSync(
    captionsPath,
    JSON.stringify(
      { journey: journeyKey, title: journey.title, subtitle: journey.subtitle, duration: Number(totalDuration.toFixed(2)), captions },
      null,
      2
    )
  );

  console.log(`\nRecorded ${journeyKey}: ${totalDuration.toFixed(1)}s`);
  console.log(`  video:    ${finalWebm}`);
  console.log(`  captions: ${captionsPath}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

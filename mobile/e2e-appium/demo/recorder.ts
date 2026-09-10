/**
 * Marketing clip recorder helpers.
 *
 * Captures the booted iOS Simulator's screen with `simctl io recordVideo`
 * (an external process — unlike Appium's in-session screen recording,
 * which wedges the WebDriver connection on real devices). One MP4 per
 * clip, written to MARKETING_OUT (default: repo marketing/recordings/).
 *
 * Used by the 90-/91-marketing-pt*.spec.ts demo drivers, which script
 * typo-free app flows so an editor (11labs) can cut feature showcases
 * from real footage.
 */
import { spawn, type ChildProcess } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { byId, swipeUp } from "../helpers/ui";

export const OUT_DIR =
  process.env.MARKETING_OUT ??
  "/Users/home/Projects/mytradeportal/marketing/recordings";

let capture: ChildProcess | null = null;
let currentClip: string | null = null;

/** Start recording the simulator screen. Only one clip at a time. */
export async function startClip(name: string): Promise<void> {
  if (currentClip) throw new Error(`clip ${currentClip} still recording`);
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const file = path.join(OUT_DIR, `${name}.mp4`);
  const udid = process.env.SIM_UDID ?? "booted";
  capture = spawn(
    "xcrun",
    ["simctl", "io", udid, "recordVideo", "--codec=h264", "--force", file],
    { stdio: "ignore" }
  );
  currentClip = name;
  // Give recordVideo a moment to attach to the display before acting.
  await driver.pause(1000);
  console.log(`[clip] recording started: ${name}`);
}

/** Stop the current clip and verify the MP4 landed on disk. */
export async function stopClip(name: string): Promise<string> {
  if (currentClip !== name) throw new Error(`clip mismatch: ${currentClip} vs ${name}`);
  const proc = capture;
  capture = null;
  currentClip = null;
  if (proc) {
    await new Promise<void>((resolve) => {
      proc.once("exit", () => resolve());
      proc.kill("SIGINT");
    });
  }
  const file = path.join(OUT_DIR, `${name}.mp4`);
  if (!fs.existsSync(file) || fs.statSync(file).size < 10_000) {
    throw new Error(`clip ${name} missing or suspiciously small: ${file}`);
  }
  const mb = (fs.statSync(file).size / 1024 / 1024).toFixed(1);
  console.log(`[clip] saved ${file} (${mb} MB)`);
  return file;
}

/** Guard: stop any dangling recording (e.g. after a failed step). */
export async function abortClip(): Promise<void> {
  if (!currentClip) return;
  const proc = capture;
  capture = null;
  if (proc) {
    try {
      await new Promise<void>((resolve) => {
        proc.once("exit", () => resolve());
        proc.kill("SIGINT");
      });
    } catch {
      /* already gone */
    }
  }
  console.log(`[clip] aborted: ${currentClip}`);
  currentClip = null;
}

/**
 * Type text visibly, character by character with human-ish jitter.
 * setValue()/addValue() paste instantly, which reads as fake in a demo —
 * this keeps keystrokes visible for the camera.
 */
export async function typeSlowly(
  el: WebdriverIO.Element | ReturnType<typeof $>,
  text: string
): Promise<void> {
  const e = (await el) as WebdriverIO.Element;
  await e.click();
  await e.clearValue();
  for (const ch of text) {
    await e.addValue(ch);
    await driver.pause(18 + Math.floor(Math.random() * 30));
  }
}

/** Tap the first element whose accessibility name contains a fragment. */
export async function tapNameContains(
  fragment: string,
  timeoutMs = 15000
): Promise<void> {
  const el = driver.$(`-ios predicate string:name CONTAINS[c] "${fragment}"`);
  await el.waitForExist({ timeout: timeoutMs });
  await el.click();
}

/** Swipe up (scroll down the page) until a testID exists, then tap it. */
export async function scrollToIdAndTap(id: string, timeoutMs = 25000): Promise<void> {
  const start = Date.now();
  while (!(await byId(id).isExisting())) {
    if (Date.now() - start > timeoutMs) throw new Error(`scrollToIdAndTap timed out: ${id}`);
    await swipeUp();
    await driver.pause(400);
  }
  await byId(id).click();
}

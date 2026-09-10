/**
 * Shared marketing clip bodies.
 *
 * Extracted from the 90-/91- specs so a single clip can be re-recorded
 * standalone (specs/92-*) without rerunning a whole batch.
 */
import {
  byId,
  dismissKeyboard,
  swipeUp,
  tapId,
  tapText,
  textElContains,
  waitForId,
  waitForText,
} from "../helpers/ui";
import { scrollToIdAndTap, startClip, stopClip, typeSlowly } from "./recorder";

/**
 * Clip 01 — AI quote drafting. Types a plain-English job description into
 * the trade intake, generates, waits for the ready banner, and reviews the
 * AI-drafted quote (confidence, assumptions, priced lines, VAT totals).
 */
export async function recordClip01AiQuoteDrafting(
  customerName: string,
  description: string
): Promise<void> {
  await startClip("01-ai-quote-drafting");
  await tapId("tab-quotes");
  await waitForText("Quotes");
  await driver.pause(1200);
  await scrollToIdAndTap("quotes-new-quote");
  const nameField = await waitForId("intake-customer-name");
  await typeSlowly(nameField, customerName);
  const desc = await waitForId("intake-description");
  await typeSlowly(desc, description);
  await dismissKeyboard();
  const chip = byId("intake-property-type-house");
  if (await chip.isExisting()) await chip.click();
  await driver.pause(600);
  await tapId("intake-generate-quote");

  // Generation is asynchronous: a banner on the Quotes list announces
  // progress, then flips to "Your AI quote is ready".
  await byId("quote-generating-banner").waitForExist({ timeout: 30000 });
  await byId("quote-ready-banner").waitForExist({ timeout: 300000, interval: 3000 });
  await driver.pause(2000);
  await (await byId("quote-ready-banner")).click();

  // Review screen: AI confidence chip, amber assumptions panel, line items.
  await textElContains("AI confidence").waitForExist({ timeout: 15000 });
  await driver.pause(2500);
  await swipeUp();
  await driver.pause(1500);
  await swipeUp();
  await driver.pause(2000);
  await stopClip("01-ai-quote-drafting");
}

/**
 * Clip 03 — review & send. Backend auto-drafts a quote from the customer's
 * request (AI triage), so there is no "new lead" step: the draft is already
 * on the Quotes list. Opens Sarah's draft, reviews the AI draft, sends.
 */
export async function recordClip03ReviewAndSend(): Promise<void> {
  await startClip("03-review-and-send");
  await tapId("tab-quotes");
  await waitForText("Quotes");
  await driver.pause(1500);
  // Sarah's request is the only one about downlights — match the card by
  // its visible label, not list position, so reruns stay deterministic.
  const card = driver.$(
    '-ios predicate string:label CONTAINS[c] "downlights"'
  );
  await card.waitForExist({ timeout: 20000 });
  await card.click();
  await waitForId("quote-line-description-0", 20000);
  await driver.pause(2500);
  await swipeUp();
  await driver.pause(1500);
  await swipeUp();
  await driver.pause(1500);
  await tapId("quote-approve-send");
  // The simulator config auto-accepts alerts, so the "Send quote?" confirm
  // may already be gone — send it manually only if it's still there.
  await tapText("Send", 8000).catch(() => undefined);
  await waitForText("Quotes", 15000);
  await driver.pause(2000);
  await stopClip("03-review-and-send");
}

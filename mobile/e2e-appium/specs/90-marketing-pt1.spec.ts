/**
 * MARKETING — part 1 (recorded on device, build 12+, prod backend).
 *
 * Fictional demo universe (seeded via API): Hartley Electrical Services Ltd
 * (tenant slug hartley-electrical, code 400334), owner Tom Hartley, and
 * customer Sarah Thompson. All data is fake: Ofcom drama phone range
 * (07700 900xxx), reserved example.com emails.
 *
 * Clips produced:
 *   01-ai-quote-drafting     — trade: new quote intake → AI generation →
 *                              ready banner → review screen (confidence,
 *                              assumptions, priced line items)
 *   02-customer-quote-request— customer: request wizard → AI chat follow-up
 *   03-review-and-send       — trade: new-lead banner → lead detail →
 *                              generate → review → send to customer
 *   06-dashboard-overview    — trade: dashboard stats, top leads, calendar
 *                              strip, notifications, settings peek
 *
 * Run:
 *   E2E_TENANT_SLUG=hartley-electrical \
 *   E2E_TRADE_EMAIL=tom@hartleyelectrical.example.com E2E_TRADE_PASSWORD='Sparky2026!' \
 *   E2E_CUSTOMER_EMAIL=sarah.thompson@example.com E2E_CUSTOMER_PASSWORD='Homeowner26!' \
 *   pnpm exec wdio run wdio.conf.ts --spec specs/90-marketing-pt1.spec.ts
 */
import { loginAsCustomer, loginAsTrade } from "../helpers/auth";
import { relaunchApp } from "../helpers/app";
import {
  byId,
  dismissKeyboard,
  handlePermissionAlert,
  swipeUp,
  tapBack,
  tapId,
  tapText,
  textElContains,
  waitForId,
  waitForText,
} from "../helpers/ui";
import { abortClip, startClip, stopClip, tapNameContains, typeSlowly } from "../demo/recorder";
import { recordClip01AiQuoteDrafting, recordClip03ReviewAndSend } from "../demo/clips";

const TOM_EMAIL = "tom@hartleyelectrical.example.com";
const TOM_PASSWORD = "Sparky2026!";
const SARAH_EMAIL = "sarah.thompson@example.com";
const SARAH_PASSWORD = "Homeowner26!";

const HELEN_DESCRIPTION =
  "Replace the consumer unit in a 3-bed semi and add four double sockets " +
  "in the kitchen and utility room. Board is in the hallway cupboard with " +
  "plenty of spare ways. Include all testing and certification.";

const SARAH_DESCRIPTION =
  "We would like six LED downlights installed in the kitchen ceiling and " +
  "two extra double sockets added — one on the kitchen island and one in " +
  "the utility room. The consumer unit has plenty of spare ways.";

afterEach(async function () {
  const state = (this as { currentTest?: { state?: string } }).currentTest?.state;
  if (state === "failed") await abortClip();
});

describe("M1: marketing clips — part 1", () => {
  before(function () {
    // LLM round-trips (quote generation, AI chat follow-up) can each take
    // minutes — disable the per-test timeout for the whole suite.
    this.timeout(0);
  });

  it("01-ai-quote-drafting", async () => {
    await loginAsTrade(TOM_EMAIL, TOM_PASSWORD);
    await waitForText("Dashboard", 25000);
    // Fresh simulator installs fire the push/location prompts on first role
    // layout mount — allow them so they never gate later taps.
    await handlePermissionAlert("allow");
    await recordClip01AiQuoteDrafting("Helen Carter", HELEN_DESCRIPTION);
  });

  it("02-customer-quote-request", async () => {
    await loginAsCustomer(SARAH_EMAIL, SARAH_PASSWORD);
    await waitForId("request-new-quote", 25000);
    await handlePermissionAlert("allow");

    await startClip("02-customer-quote-request");
    await tapId("request-new-quote");
    await waitForId("quote-postcode-input", 15000);
    const postcode = await waitForId("quote-postcode-input");
    await typeSlowly(postcode, "HG2 8JR");
    await dismissKeyboard();
    await tapId("quote-check-area");

    // Contact step (pre-filled from the account — pick comms preference).
    await waitForId("quote-name-input", 15000);
    await tapText("Online chat", 15000);
    await tapId("quote-contact-continue", 15000);

    // Property profile.
    await waitForId("quote-property-continue", 15000);
    await tapText("Terrace", 15000);
    await tapText("Not sure", 15000);
    await tapText("Owner", 15000);
    await tapText("Yes", 15000);
    await tapId("quote-property-continue", 15000);

    // Category + free-text description.
    await tapId("quote-category-other", 15000);
    await tapId("quote-category-continue", 15000);
    await waitForId("quote-other-continue", 15000);
    const textViews = await (
      await $$("-ios class chain:**/XCUIElementTypeTextView")
    ).getElements();
    const notes = textViews[0];
    if (!notes) throw new Error("description TextView not found");
    await typeSlowly(notes, SARAH_DESCRIPTION);
    await dismissKeyboard();
    await tapId("quote-other-continue", 15000);

    // Photos: skip. Urgency: Flexible, no date chip.
    await waitForId("quote-media-continue", 15000);
    await tapId("quote-media-continue", 15000);
    await waitForId("quote-urgency-continue", 15000);
    await tapText("Flexible", 15000);
    await tapId("quote-urgency-continue", 15000);

    // Budget (all optional) → consents → submit.
    await waitForId("quote-budget-continue", 15000);
    await tapId("quote-budget-continue", 15000);
    await waitForId("quote-submit", 15000);
    await tapId("quote-consent-terms");
    await tapId("quote-consent-contact");
    await tapId("quote-submit", 25000);

    // Confirmation, then into the AI chat for the follow-up.
    await textElContains("has your request").waitForExist({ timeout: 25000 });
    await driver.pause(3000);
    await tapId("quote-done", 15000);
    await driver.pause(1000);
    await tapId("customer-ai-banner", 25000);
    await waitForText("Messages", 20000);
    // The first follow-up auto-fires on open (LLM round-trip — poll patiently).
    await byId("chat-message-agent").waitForExist({ timeout: 240000, interval: 3000 });
    await driver.pause(2000);
    const composer = await waitForId("chat-composer");
    await typeSlowly(composer, "That covers everything, thank you!");
    await tapId("chat-send");
    await byId("chat-message-customer").waitForExist({ timeout: 15000 });
    await driver.pause(2000);
    await stopClip("02-customer-quote-request");
  });

  it("03-review-and-send", async () => {
    await loginAsTrade(TOM_EMAIL, TOM_PASSWORD);
    await waitForText("Dashboard", 25000);
    await handlePermissionAlert("allow");
    await recordClip03ReviewAndSend();
  });

  it("06-dashboard-overview", async () => {
    await relaunchApp();
    await waitForText("Dashboard", 25000);

    await startClip("06-dashboard-overview");
    await driver.pause(3000);
    await swipeUp();
    await driver.pause(2000);
    await swipeUp();
    await driver.pause(2000);
    await tapId("tab-dashboard");
    await driver.pause(1500);
    await tapId("notifications-bell-trade");
    await driver.pause(2500);
    await tapBack();
    await driver.pause(1000);
    await tapId("dashboard-more");
    await driver.pause(2500);
    await stopClip("06-dashboard-overview");
  });
});

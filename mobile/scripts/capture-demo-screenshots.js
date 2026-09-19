#!/usr/bin/env node
/**
 * Captures demo screenshots of the interactive mock iOS app running in web mode.
 *
 * Run from the repo root after starting the Expo web dev server:
 *   cd mobile && npx expo start --web --port 8084
 *   # in another shell:
 *   node mobile/scripts/capture-demo-screenshots.js
 */
const { chromium } = require("playwright");
const fs = require("node:fs");
const path = require("node:path");

const BASE_URL = process.env.DEMO_BASE_URL || "http://localhost:8084";
const OUT_DIR = path.resolve("mobile/demo-screenshots");

const VIEWPORT = { width: 390, height: 844 };

let counter = 1;

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function tapByText(page, text) {
  const byTestId = page.locator(`[data-testid*="${text.toLowerCase().replace(/\s+/g, "-")}"]`);
  if ((await byTestId.count()) > 0) {
    await byTestId.first().click({ force: true });
  } else {
    await page.getByText(text).first().click({ force: true });
  }
  await sleep(400);
}

async function tapTestId(page, testId, settleMs = 800) {
  const locator = page.locator(`[data-testid="${testId}"]:visible`).first();
  const count = await locator.count();
  if (count === 0) {
    await page.locator(`[data-testid="${testId}"]`).first().click({ force: true });
  } else {
    await locator.click();
  }
  await sleep(settleMs);
}

async function typeInPlaceholder(page, placeholder, value) {
  const input = page.getByPlaceholder(placeholder).first();
  await input.fill(value);
  await sleep(200);
}

async function typeCode(page, code) {
  const first = page.locator("input").first();
  await first.click();
  await sleep(200);
  await first.pressSequentially(code);
  await sleep(400);
}

async function typeInInput(page, index, value) {
  const input = page.locator("input, textarea").nth(index);
  await input.fill(value);
  await sleep(200);
}

async function capture(page, name) {
  await fs.promises.mkdir(OUT_DIR, { recursive: true });
  const fileName = `${String(counter).padStart(2, "0")}-${name}`;
  const filePath = path.join(OUT_DIR, `${fileName}.png`);
  await page.screenshot({ path: filePath, fullPage: false });
  console.log(`Captured ${filePath}`);
  counter += 1;
  return filePath;
}

async function main() {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: VIEWPORT });
  const page = await context.newPage();

  await page.goto(BASE_URL, { waitUntil: "networkidle" });
  await sleep(1500);

  // 1. Entry / business code lookup
  await capture(page, "entry");
  await typeCode(page, "123456");
  await tapTestId(page, "entry-find-business");

  // 2. Branded customer landing page
  await capture(page, "business-selected");
  await tapTestId(page, "back-button");
  await sleep(400);

  // 3. Electrician login
  await tapTestId(page, "entry-trade-login");
  await capture(page, "trade-login");
  await typeInInput(page, 0, "owner@demo.trade");
  await typeInInput(page, 1, "demo123");
  await tapByText(page, "Sign in");
  await sleep(1200);

  // 4. Dashboard
  await capture(page, "dashboard");

  // 5. Lead detail from dashboard (one tap to action)
  await tapByText(page, "Consumer unit upgrade");
  await sleep(400);
  await capture(page, "lead-detail");

  // 6. Quote intake
  await tapByText(page, "Generate AI quote");
  await sleep(400);
  await capture(page, "quote-intake");
  await tapTestId(page, "intake-property-type-house");
  await tapTestId(page, "intake-bedrooms-3");
  await tapTestId(page, "intake-cu-location-hallway");
  await typeInPlaceholder(page, "e.g. Driveway parking, key-safe code 1234", "Driveway parking");
  await typeInPlaceholder(page, "Any access restrictions, pets, working hours...", "Dog on site");
  await tapTestId(page, "intake-generate-quote");
  await sleep(1400);

  // 7. Quote edit (time & materials)
  await capture(page, "quote-edit");

  // 8. In-app chat request for more info
  await tapTestId(page, "quote-more-actions");
  await tapTestId(page, "quote-request-info");
  await sleep(600);
  await capture(page, "request-info-chat");
  await tapTestId(page, "back-button");
  await sleep(400);

  // 9. Per-point pricing
  await tapTestId(page, "pricing-per_point");
  await capture(page, "quote-edit-per-point");
  await sleep(400);
  await tapTestId(page, "back-button");
  await sleep(400);

  // 10. Quotes tab
  await tapTestId(page, "tab-quotes");
  await capture(page, "quotes");

  // 11. Customers tab
  await tapTestId(page, "tab-customers");
  await capture(page, "customers");
  await tapTestId(page, "customer-card-c1");
  await capture(page, "customer-detail");
  await tapByText(page, "Quotes");
  await capture(page, "customer-quotes");
  await tapTestId(page, "back-button");
  await sleep(400);
  await tapTestId(page, "back-button");
  await sleep(400);

  // 12. Calendar day view
  await tapTestId(page, "tab-calendar");
  await capture(page, "calendar-day");

  // 13. Calendar week view
  await tapTestId(page, "calendar-week", 800);
  await capture(page, "calendar-week");

  // 14. Settings (open from Calendar header; avoids Dashboard nested-screen state)
  await tapTestId(page, "settings", 800);
  await capture(page, "settings");

  // 15. Follow-up settings
  await tapTestId(page, "settings-follow-ups");
  await capture(page, "follow-up-settings");
  await tapTestId(page, "back-button");
  await sleep(400);

  // 16. Branding
  await tapTestId(page, "settings-branding");
  await capture(page, "branding");
  await tapTestId(page, "back-button");
  await sleep(400);

  // 17. AI manual lead entry from dashboard
  await tapTestId(page, "tab-dashboard");
  await sleep(400);
  await tapByText(page, "+ New lead");
  await capture(page, "ai-lead-entry");
  await tapTestId(page, "back-button");
  await sleep(400);

  // 18. External contact fallback (unregistered WhatsApp lead)
  await tapByText(page, "EV charger install");
  await sleep(400);
  await tapTestId(page, "lead-request-info");
  await sleep(600);
  await capture(page, "request-info-external");
  await tapTestId(page, "back-button");
  await sleep(400);
  await tapTestId(page, "back-button");
  await sleep(400);
  await tapTestId(page, "back-button");
  await sleep(400);

  // 19. Customer journey: log out and sign in as customer
  await tapTestId(page, "dashboard-more");
  await sleep(400);
  await tapTestId(page, "settings-logout");
  await sleep(800);

  // 20. Entry screen, customer login
  await capture(page, "entry-after-logout");
  await tapTestId(page, "entry-customer-login");
  await sleep(400);
  await capture(page, "customer-login");
  await typeInInput(page, 0, "jane@example.com");
  await typeInInput(page, 1, "demo123");
  await tapByText(page, "Sign in");
  await sleep(1200);

  // 21. Customer quotes list
  await capture(page, "customer-quotes");

  // 22. View full quote
  await tapByText(page, "View full quote");
  await sleep(400);
  await capture(page, "customer-quote-detail");

  // 23. Accept and book a date
  await tapByText(page, "Accept quote");
  await sleep(400);
  await capture(page, "customer-quote-accepted");
  await tapTestId(page, "customer-book-date");
  await sleep(400);
  await capture(page, "customer-book-date");
  await tapTestId(page, "book-day-1");
  await sleep(200);
  await tapTestId(page, "book-time-1");
  await sleep(200);
  await tapByText(page, "Confirm booking");
  await sleep(400);

  // 24. Editable profile
  await tapTestId(page, "tab-profile");
  await sleep(400);
  await capture(page, "customer-profile");

  await browser.close();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

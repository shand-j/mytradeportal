#!/usr/bin/env node
/**
 * Captures customer-flow demo screenshots of the interactive mock iOS app.
 *
 * Run after starting the Expo web dev server:
 *   cd mobile && npx expo start --web
 *   node mobile/scripts/capture-customer-screenshots.js
 */
const { chromium } = require("playwright");
const fs = require("node:fs");
const path = require("node:path");

const BASE_URL = process.env.DEMO_BASE_URL || "http://localhost:8081";
const OUT_DIR = path.resolve("mobile/demo-screenshots");

const VIEWPORT = { width: 390, height: 844 };

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function tapByText(page, text) {
  // React Native Web Pressable events are most reliably triggered by clicking
  // the element directly rather than the text node.
  const byTestId = page.locator(`[data-testid*="${text.toLowerCase().replace(/\s+/g, "-")}"]`);
  if ((await byTestId.count()) > 0) {
    await byTestId.first().click({ force: true });
  } else {
    await page.getByText(text).first().click({ force: true });
  }
  await sleep(400);
}

async function tapTestId(page, testId) {
  await page.locator(`[data-testid="${testId}"]`).first().click({ force: true });
  await sleep(400);
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

async function capture(page, name) {
  await fs.promises.mkdir(OUT_DIR, { recursive: true });
  const filePath = path.join(OUT_DIR, `${name}.png`);
  await page.screenshot({ path: filePath, fullPage: false });
  console.log(`Captured ${filePath}`);
  return filePath;
}

async function main() {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: VIEWPORT });
  const page = await context.newPage();

  await page.goto(BASE_URL, { waitUntil: "networkidle" });
  await sleep(1500);

  await typeCode(page, "123456");
  await tapTestId(page, "entry-find-business");
  await capture(page, "21-customer-entry");

  await tapTestId(page, "entry-request-quote");
  await capture(page, "22-customer-postcode");

  await typeInPlaceholder(page, "Enter your postcode", "SK8 3NJ");
  await tapTestId(page, "quote-check-area");
  await capture(page, "23-customer-contact");

  await typeInPlaceholder(page, "Full name", "Jane Homeowner");
  await typeInPlaceholder(page, "Email", "jane@example.com");
  await typeInPlaceholder(page, "Create password", "demo123");
  await tapTestId(page, "quote-contact-continue");
  await capture(page, "24-customer-property");

  await tapByText(page, "House");
  await tapTestId(page, "quote-property-continue");
  await capture(page, "25-customer-category");

  await tapByText(page, "Consumer unit");
  await capture(page, "26-customer-urgency");

  await tapByText(page, "This month");
  await tapTestId(page, "quote-urgency-continue");
  await capture(page, "27-customer-media");

  await tapTestId(page, "quote-media-continue");
  await capture(page, "28-customer-confirmation");

  await tapTestId(page, "quote-track-button");
  await capture(page, "29-customer-dashboard");

  await browser.close();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

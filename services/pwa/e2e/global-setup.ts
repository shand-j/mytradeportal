import { chromium } from "@playwright/test";

const PORT = process.env.E2E_WEB_PORT ?? "8090";
const BASE_URL = `http://localhost:${PORT}`;

/**
 * Pre-warm the Expo web bundle before the suite runs. The first page load
 * triggers a full Metro build (slow, especially with --clear); doing it once
 * here keeps individual tests from flaking on the cold-build cost.
 */
async function globalSetup(): Promise<void> {
  const browser = await chromium.launch({
    args: ["--disable-web-security", "--disable-features=IsolateOrigins,site-per-process"],
  });
  const page = await browser.newPage();
  try {
    await page.goto(BASE_URL, { waitUntil: "networkidle", timeout: 240000 });
    // The generic build opens on "My Trade Portal"; a white-label build opens on
    // the branded "Your electrician" entry. Wait for whichever renders.
    await page
      .getByText(/My Trade Portal|Your electrician/)
      .first()
      .waitFor({ state: "visible", timeout: 240000 });
  } finally {
    await page.close();
    await browser.close();
  }
}

export default globalSetup;

import { expect, Page } from "@playwright/test";

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Tap an element by testID, preferring the visible instance. expo-router keeps
 * previous screens mounted (hidden) in the DOM on web, so a plain `.first()`
 * can resolve a stale hidden element.
 */
export async function tap(page: Page, testId: string, settleMs = 400): Promise<void> {
  const visible = page.locator(`[data-testid="${testId}"]:visible`).first();
  const any = page.locator(`[data-testid="${testId}"]`).first();
  const locator = (await visible.count()) > 0 ? visible : any;
  await locator.waitFor({ state: "visible", timeout: 20000 });
  await locator.click({ force: true });
  await sleep(settleMs);
}

/** Tap the visible element that renders the given (partial) text. */
export async function tapText(page: Page, text: string, settleMs = 400): Promise<void> {
  const locator = page.getByText(text, { exact: false }).locator("visible=true").first();
  await locator.waitFor({ state: "visible", timeout: 20000 });
  await locator.click({ force: true });
  await sleep(settleMs);
}

/** Wait until (partial) text is visible anywhere on the page. */
export async function waitText(page: Page, text: string, timeout = 30000): Promise<void> {
  await page
    .getByText(text, { exact: false })
    .locator("visible=true")
    .first()
    .waitFor({ state: "visible", timeout });
}

/** The current visible page text (for coarse content assertions). */
export async function bodyText(page: Page): Promise<string> {
  return page.locator("body").innerText();
}

/**
 * Log in as the seeded demo trade owner from the entry screen. Assumes the app
 * is in connected mode (EXPO_PUBLIC_API_BASE_URL set) with no business slug, so
 * the entry screen shows the "Electrician login" option and the login form is
 * pre-filled with the demo credentials that the seed script provisions.
 */
export async function loginAsTradeOwner(page: Page): Promise<void> {
  await page.goto("/", { waitUntil: "networkidle" });
  // First navigation triggers a cold Expo web bundle (slow, especially --clear).
  await waitText(page, "My Trade Portal", 120000);
  await tap(page, "entry-trade-login");
  await waitText(page, "Electrician login");
  await tapText(page, "Sign in");
  await waitText(page, "Top leads", 30000);
}

export { sleep, expect };

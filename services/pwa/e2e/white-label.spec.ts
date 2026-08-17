import { test, expect } from "@playwright/test";
import { waitText, bodyText } from "./helpers";

// A per-tenant white-label build (EXPO_PUBLIC_BUSINESS_SLUG set) fetches the
// business's public config on launch and opens branded for that tenant, rather
// than the generic marketplace 6-digit code entry.

test("app boots branded from the real public config", async ({ page }) => {
  await page.goto("/", { waitUntil: "networkidle" });
  await waitText(page, "Your electrician", 60000);

  const body = await bodyText(page);
  expect(body).toMatch(/Demo Electrical/); // real tenant name from the API
  expect(body).toMatch(/Request a quote/); // branded customer entry
  expect(body).not.toMatch(/6-digit code/); // not the generic marketplace screen
});

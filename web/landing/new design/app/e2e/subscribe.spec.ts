import { expect, test } from "@playwright/test";

test("free-beta subscribe page does not initialize Paddle", async ({ page }) => {
  const paddleRequests: string[] = [];
  page.on("request", (request) => {
    const hostname = new URL(request.url()).hostname;
    if (hostname === "paddle.com" || hostname.endsWith(".paddle.com")) {
      paddleRequests.push(request.url());
    }
  });

  await page.goto("/subscribe", { waitUntil: "networkidle" });
  await expect(page.getByText("Billing is paused for beta")).toBeVisible();
  await expect(
    page.getByText(/invited beta businesses keep full access for free/i),
  ).toBeVisible();
  expect(paddleRequests).toEqual([]);
});

import { expect, test } from "@playwright/test";

test("legal routes render and expose policy links", async ({ page }) => {
  await page.goto("/terms");
  await expect(page.getByRole("heading", { name: "Terms of Service" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Fair-use policy", exact: true })).toHaveAttribute(
    "href",
    "/fair-use",
  );
  await expect(page.getByRole("link", { name: "Privacy", exact: true }).first()).toBeVisible();

  await page.goto("/privacy");
  await expect(page.getByRole("heading", { name: "Privacy notice" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Terms", exact: true }).first()).toBeVisible();
  await expect(page.getByText("AI-assisted quote and follow-up processing")).toBeVisible();
  await expect(page.getByText("Payments and PCI posture")).toBeVisible();
  await expect(page.getByText("My Trade Portal never receives or stores", { exact: false })).toBeVisible();

  await page.goto("/fair-use");
  await expect(page.getByRole("heading", { name: "Fair-use policy" })).toBeVisible();
  await expect(page.getByText(/around 500 AI actions a month/i)).toBeVisible();
  await expect(page.getByText(/always talk to you before limiting anything/i)).toBeVisible();
  await expect(page.getByText(/never a hard block without a human reviewing/i)).toBeVisible();

  await page.goto("/");
  await expect(page.locator("#pricing").getByRole("link", { name: "fair-use policy" })).toHaveAttribute(
    "href",
    "/fair-use",
  );
  await expect(page.locator("footer").getByRole("link", { name: "Fair use" })).toHaveAttribute(
    "href",
    "/fair-use",
  );
});

test("tenant portal legal routes stay in portal mode", async ({ page }) => {
  await page.goto("/terms?slug=demo");
  await expect(page.getByRole("heading", { name: "Terms of Service" })).toBeVisible();

  await page.goto("/privacy?slug=demo");
  await expect(page.getByRole("heading", { name: "Privacy notice" })).toBeVisible();
});

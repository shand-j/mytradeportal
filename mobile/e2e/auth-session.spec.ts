import { test } from "@playwright/test";
import {
  createTestTenant,
  expect,
  fill,
  gotoEntryRole,
  loginAsTradeOwner,
  sleep,
  tap,
  waitText,
} from "./helpers";

test.describe.serial("Auth/session restore regressions", () => {
  test("restores trade session after cold reload", async ({ page }) => {
    const tenant = await createTestTenant("auth-restore");
    await loginAsTradeOwner(page, tenant);

    await page.reload({ waitUntil: "networkidle" });
    await page.getByText("Dashboard").first().waitFor({ state: "visible", timeout: 30_000 });
  });

  test("invalid stored token resolves to signed-out entry without repeated auth churn", async ({
    page,
  }) => {
    const tenant = await createTestTenant("auth-invalid");
    const authProbe: string[] = [];
    page.on("request", (request) => {
      const url = request.url();
      if (url.endsWith("/auth/me") || url.endsWith("/customer/me")) {
        authProbe.push(url);
      }
    });

    await page.addInitScript(
      ({ token, tenantId }) => {
        localStorage.setItem("mtp_auth_token", token);
        localStorage.setItem("mtp_tenant_id", tenantId);
      },
      { token: "invalid-token", tenantId: tenant.tenantId }
    );

    await page.goto("/", { waitUntil: "networkidle" });
    await page.locator('[data-testid="role-select"]').waitFor({ state: "visible", timeout: 30_000 });
    await sleep(2_500);

    expect(authProbe.length).toBeLessThanOrEqual(3);
  });

  test("api-offline cold-start does not clear token and auto-recovers when back online", async ({
    page,
  }) => {
    const tenant = await createTestTenant("auth-offline");
    await loginAsTradeOwner(page, tenant);

    await page.route(`${tenant.base}/**`, (route) => route.abort("internetdisconnected"));
    await page.reload({ waitUntil: "networkidle" });
    await page.locator('[data-testid="role-select"]').waitFor({ state: "visible", timeout: 30_000 });

    await page.unroute(`${tenant.base}/**`);
    await page.reload({ waitUntil: "networkidle" });
    const dashboardTab = page.locator('[data-testid="tab-dashboard"]');
    const onboardingContinue = page.getByText("Continue", { exact: false }).first();
    await dashboardTab.or(onboardingContinue).waitFor({ state: "visible", timeout: 30_000 });
    await expect(page.locator('[data-testid="role-select"]')).toHaveCount(0);
  });

  test("rate-limited login shows throttling guidance instead of invalid credentials", async ({
    page,
  }) => {
    await page.route("**/auth/token", (route) =>
      route.fulfill({
        status: 429,
        contentType: "application/json",
        body: JSON.stringify({ detail: "rate limited" }),
      })
    );

    await gotoEntryRole(page, "trade");
    await tap(page, "entry-trade-login");
    await waitText(page, "Electrician login");
    await fill(page, "login-email", "owner@example.com");
    await fill(page, "login-password", "not-a-real-password");
    await tap(page, "login-submit");

    await waitText(page, "Too many sign-in attempts. Please wait a minute and try again.");
    await expect(page.getByText("Invalid email or password.")).toHaveCount(0);
  });
});

// G24 — Password reset (both roles): single-use signed token, branded pages
// on the marketing origin and the tenant portal variant, no account-existence
// leak. The reset panel is shared (src/portal/reset/ResetPasswordPanel.tsx);
// only the chrome differs.
//
// See docs/e2e-coverage-gaps.md row G24.

import { expect, type Page } from "@playwright/test";
import { mailpitConfigured, waitForEmail, assertNoEmail } from "./mailpit";
import {
  createTenant,
  loginCustomer,
  registerCustomer,
  stagingConfigured,
  uniqueEmail,
  type Tenant,
  portalTest as test,
} from "./helpers";

let tenant: Tenant;

const API = process.env.TEST_API_BASE_URL ?? "";

async function requestReset(email: string): Promise<{ status: number }> {
  const res = await fetch(`${API}/auth/password-reset/request`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  return { status: res.status };
}

/** Follow a reset link on the given origin and set a new password. */
async function completeReset(
  page: Page,
  pathWithToken: string,
  expectedEmail: string,
  newPassword: string,
): Promise<void> {
  await page.goto(pathWithToken, { waitUntil: "domcontentloaded" });
  await expect(page.getByText(expectedEmail)).toBeVisible({ timeout: 60_000 });
  await page.locator("#new-password").fill(newPassword);
  await page.locator("#confirm-password").fill(newPassword);
  await page.getByRole("button", { name: "Set new password" }).click();
  await expect(page.getByText(`Password updated for ${expectedEmail}`)).toBeVisible();
}

test.beforeAll(async () => {
  test.skip(!stagingConfigured(), "TEST_API_BASE_URL / TEST_SETUP_TOKEN not set");
  test.skip(!mailpitConfigured(), "MAILPIT_URL / MAILPIT_BASIC_AUTH not set");
  tenant = await createTenant("portal-reset");
});

test("trade account: full reset journey on the marketing origin", async ({ page }) => {
  const request = await requestReset(tenant.adminEmail);
  expect(request.status).toBe(200);

  const mail = await waitForEmail(tenant.adminEmail, {
    subjectIncludes: "Reset your My Trade Portal password",
  });
  const token = extractResetToken(mail.text + mail.html);
  await completeReset(page, `/reset-password?token=${token}`, tenant.adminEmail, "Reset-admin-1");

  // The new password works; the old one does not.
  const login = await fetch(`${API}/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email: tenant.adminEmail,
      password: "Reset-admin-1",
      tenant_slug: tenant.slug,
    }),
  });
  expect(login.status).toBe(200);
  const oldLogin = await fetch(`${API}/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email: tenant.adminEmail,
      password: tenant.adminPassword,
      tenant_slug: tenant.slug,
    }),
  });
  expect(oldLogin.status).toBe(401);

  // Single-use: replaying the consumed token shows the invalid state.
  await page.goto(`/reset-password?token=${token}`, { waitUntil: "domcontentloaded" });
  await expect(page.getByText(/invalid or has expired/i)).toBeVisible();
});

test("customer account reset works too (both roles)", async ({ page }) => {
  const email = uniqueEmail("reset-customer");
  await registerCustomer(tenant, {
    email,
    password: "Original-1-x",
    fullName: "Reset Customer",
  });

  await requestReset(email);
  const mail = await waitForEmail(email, { subjectIncludes: "Reset your My Trade Portal" });
  const token = extractResetToken(mail.text + mail.html);
  await completeReset(page, `/reset-password?token=${token}`, email, "Replacement-1-x");

  const login = await loginCustomer(tenant, { email, password: "Replacement-1-x" });
  expect(login.status).toBe(200);
});

test("portal-branded reset page renders inside tenant chrome", async ({ page }) => {
  const request = await requestReset(tenant.adminEmail);
  expect(request.status).toBe(200);
  const mail = await waitForEmail(tenant.adminEmail, {
    subjectIncludes: "Reset your My Trade Portal password",
  });
  const token = extractResetToken(mail.text + mail.html);

  await page.goto(
    `/reset-password?token=${encodeURIComponent(token)}&slug=${encodeURIComponent(tenant.slug)}`,
    { waitUntil: "domcontentloaded" },
  );
  // Portal chrome (tenant-branded header), not marketing Nav/Footer.
  await expect(page.getByText("Customer portal").first()).toBeVisible();
  await expect(page.getByText(tenant.name).first()).toBeVisible();
  await expect(page.getByText(tenant.adminEmail)).toBeVisible();
  await page.locator("#new-password").fill("Portal-reset-1");
  await page.locator("#confirm-password").fill("Portal-reset-1");
  await page.getByRole("button", { name: "Set new password" }).click();
  await expect(page.getByText(`Password updated for ${tenant.adminEmail}`)).toBeVisible();
});

test("reset request never reveals whether an account exists", async () => {
  const unknown = uniqueEmail("reset-nobody");
  const request = await requestReset(unknown);
  expect(request.status).toBe(200);
  await assertNoEmail(unknown, { windowMs: 12_000 });
});

function extractResetToken(body: string): string {
  const match =
    body.match(/reset-password\?token=([a-zA-Z0-9_\-]+)/) ??
    body.match(/token=([a-zA-Z0-9_\-]+)/);
  if (!match) throw new Error("no reset token found in email");
  return match[1];
}

import { test, expect } from './fixtures';
import {
  createCustomer,
  createQuote,
  createInvoice,
  createJob,
} from './helpers';

const djangoUsername = process.env.E2E_DJANGO_ADMIN_USERNAME ?? 'superadmin';
const djangoPassword = process.env.E2E_DJANGO_ADMIN_PASSWORD ?? '';
const adminBaseUrl = process.env.E2E_ADMIN_BASE_URL ?? 'http://localhost:8001';

// Skip the whole suite if no production superuser password is configured.
test.skip(!djangoPassword, 'E2E_DJANGO_ADMIN_PASSWORD is not set');

test.describe('production smoke test', () => {
  test.use({ storageState: undefined });

  let tenantSlug = '';
  let tenantName = '';
  let adminEmail = '';
  const adminPassword = 'smoke-admin-pass-123';

  test.beforeEach(async ({ page }) => {
    const id = `e2e-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    tenantSlug = `prod-smoke-${id}`;
    tenantName = `Prod Smoke ${id}`;
    adminEmail = `admin-${id}@example.com`;

    // 1. Log in to the Django admin panel using the production superuser.
    await page.goto(`${adminBaseUrl}/admin/login/`);
    await page.getByLabel('Username:').fill(djangoUsername);
    await page.getByLabel('Password:').fill(djangoPassword);
    await page.getByRole('button', { name: 'Log in' }).click();
    await expect(page).toHaveURL(`${adminBaseUrl}/admin/`);

    // 2. Create a temporary tenant for the smoke test.
    await page.goto(`${adminBaseUrl}/admin/operations/tenant/add/`);
    await page.getByLabel('Name:').fill(tenantName);
    await page.getByLabel('Slug:').fill(tenantSlug);
    await page.getByRole('button', { name: 'Save', exact: true }).click();
    await expect(page.getByText('was added successfully')).toBeVisible();

    // 3. Create the first staff user for that tenant.
    await page.goto(`${adminBaseUrl}/admin/operations/user/add/`);
    await page.locator('select[name="tenant"]').selectOption({ label: tenantName });
    await page.getByLabel('Email:').fill(adminEmail);
    await page.getByLabel('Full name:').fill('Smoke Test Admin');
    await page.getByLabel('Role:').fill('admin');
    await page.getByLabel('Password:', { exact: true }).fill(adminPassword);
    await page.getByRole('button', { name: 'Save', exact: true }).click();
    await expect(page.getByText('was added successfully')).toBeVisible();

    // 4. Persist the tenant slug so the teardown step can clean it up.
    process.env.E2E_SMOKE_TENANT_SLUG = tenantSlug;
    // Also write it to disk for CI teardown steps that run in a separate process.
    const fs = await import('fs');
    const path = await import('path');
    const tmpDir = process.env.E2E_ARTIFACT_DIR ?? 'playwright/.tmp';
    fs.mkdirSync(tmpDir, { recursive: true });
    fs.writeFileSync(path.join(tmpDir, 'prod-smoke-tenant.json'), JSON.stringify({ tenantSlug, tenantName, adminEmail }));
  });

  test('smoke: customer, quote, invoice and job', async ({ page }) => {
    test.setTimeout(90_000); // allow slower prod env just for this smoke flow

    // 5. Log in to the back-office UI as the new tenant admin.
    await page.goto('/login');
    await page.getByLabel(/business slug/i).fill(tenantSlug);
    await page.getByLabel(/email/i).fill(adminEmail);
    await page.getByLabel(/password/i).fill(adminPassword);

    await page.getByRole('button', { name: /sign in/i }).click();

    // Prefer a stable "logged-in" signal over a brittle navigation wait.
    await expect(page.getByText('Smoke Test Admin')).toBeVisible({ timeout: 30_000 });

    // Keep URL validation flexible for route differences (/ vs /dashboard).
    await expect(page).toHaveURL(/\/($|dashboard)/, { timeout: 30_000 });

    // 6. Exercise core functionality.
    const customerName = await createCustomer(page, tenantSlug);

    const quoteRef = await createQuote(page, customerName, tenantSlug);
    await page.goto('/quotes');
    await expect(page.getByRole('link', { name: quoteRef })).toBeVisible();

    const invoiceRef = await createInvoice(page, customerName, tenantSlug);
    await page.goto('/invoices');
    await expect(page.getByRole('link', { name: invoiceRef })).toBeVisible();

    const jobRef = await createJob(page, customerName, tenantSlug);
    await page.goto('/jobs');
    await expect(page.getByText(jobRef)).toBeVisible();
  });
});

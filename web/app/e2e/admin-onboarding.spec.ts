import { test, expect } from './fixtures';

test.use({ storageState: undefined });

test('Django admin can create the first tenant and staff user', async ({ page, testId }) => {
  test.setTimeout(120_000);

  const djangoUsername = process.env.E2E_DJANGO_ADMIN_USERNAME ?? 'superadmin';
  const djangoPassword = process.env.E2E_DJANGO_ADMIN_PASSWORD ?? 'super-password-123';
  const tenantSlug = `first-customer-${testId}`;
  const tenantName = `First Customer ${testId}`;
  const adminEmail = `admin-${testId}@example.com`;
  const adminPassword = 'first-admin-pass-123';

  const adminBaseUrl = process.env.E2E_ADMIN_BASE_URL ?? 'http://localhost:8001';

  // 1. Log in to the Django admin panel.
  await page.goto(`${adminBaseUrl}/admin/login/`);
  await page.getByLabel('Username:').fill(djangoUsername);
  await page.getByLabel('Password:').fill(djangoPassword);
  await page.getByRole('button', { name: 'Log in' }).click();
  await expect(page).toHaveURL(`${adminBaseUrl}/admin/`);

  // 2. Create a new tenant.
  await page.goto(`${adminBaseUrl}/admin/operations/tenant/add/`);
  await page.getByLabel('Name:').fill(tenantName);
  await page.getByLabel('Slug:').fill(tenantSlug);
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(page.getByText('was added successfully')).toBeVisible();

  // 3. Create the first staff user for that tenant.
  await page.goto(`${adminBaseUrl}/admin/operations/user/add/`);
  await page.locator('select[name="tenant"]').selectOption({ label: tenantName });
  await page.getByLabel('Email:').fill(adminEmail);
  await page.getByLabel('Full name:').fill('First Customer Admin');
  await page.getByLabel('Role:').fill('admin');
  await page.locator('input[name="password"]').fill(adminPassword);
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(page.getByText('was added successfully')).toBeVisible();

  // 4. Log in to the back-office UI as the new staff user.
  await page.goto('/login');
  await page.getByLabel(/business slug/i).fill(tenantSlug);
  await page.getByLabel(/email/i).fill(adminEmail);
  await page.getByLabel(/password/i).fill(adminPassword);
  await page.getByRole('button', { name: /sign in/i }).click();
  await page.waitForURL('**/');
  await expect(page).toHaveURL('/');
  await expect(page.getByText('First Customer Admin')).toBeVisible();
  await expect(page.getByText('Revenue This Month')).toBeVisible();
});

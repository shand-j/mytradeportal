import { test, expect } from './fixtures';

test('update and persist business settings', async ({ page, testId }) => {
  const newName = `E2E Electrical ${testId}`;

  await page.goto('/settings');
  await page.getByLabel(/business name/i).fill(newName);

  const savePromise = page.waitForResponse((res) => res.url().includes('/tenants/me') && res.request().method() === 'PATCH');
  await page.getByRole('button', { name: /save business/i }).click();
  await savePromise;

  await page.goto('/dashboard');
  await page.goto('/settings');
  await expect(page.getByLabel(/business name/i)).toHaveValue(newName);
});

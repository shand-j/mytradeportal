import { test, expect } from './fixtures';
import { createCustomer } from './helpers';

test('add a customer and view their profile', async ({ page, testId }) => {
  const customerName = await createCustomer(page, testId);

  await page.goto('/customers');
  await expect(page.getByRole('heading', { name: /customers/i, level: 2 })).toBeVisible();

  const card = page.locator('.rounded-xl', { hasText: customerName }).first();
  await expect(card).toBeVisible();
  await expect(card.getByText('07700 000000')).toBeVisible();

  await card.getByRole('link').click();
  await page.waitForURL(/\/customers\/[0-9a-f-]+$/);
  await expect(page.getByRole('heading', { name: customerName })).toBeVisible();

  await expect(page.getByRole('link', { name: 'Schedule Job' })).toHaveAttribute(
    'href',
    /\/jobs\?customerId=.+/,
  );
  await expect(page.getByRole('link', { name: /Log Call/ })).toHaveAttribute(
    'href',
    /^tel:/,
  );

  await page.getByRole('link', { name: 'Schedule Job' }).click();
  await page.waitForURL(/\/jobs\?customerId=.+/);
  await expect(page.getByRole('heading', { name: 'New Job' })).toBeVisible();
  await expect(page.getByRole('combobox').first()).not.toHaveValue('');
});

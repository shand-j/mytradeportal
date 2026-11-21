import { expect, test } from '@playwright/test'

test('help content describes the free beta without paid-trial claims', async ({ page }) => {
  await page.goto('/help/getting-started')
  await expect(page.getByText(/free beta access/i).first()).toBeVisible()
  await expect(page.getByText(/Paddle billing is paused/i)).toBeVisible()
  await expect(page.getByText(/14-day free trial/i)).toHaveCount(0)
  await expect(page.getByText(/billed by Paddle/i)).toHaveCount(0)

  await page.goto('/help/faq')
  await expect(page.getByRole('heading', { name: 'What happens during the beta?' })).toBeVisible()
  await expect(page.getByText(/no paid trial/i)).toBeVisible()
  await expect(page.getByText(/Paddle billing is paused/i)).toBeVisible()
})

test('blog states scheduling and job tracking are available', async ({ page }) => {
  await page.goto('/blog/tradify-jobber-alternatives')
  await expect(page.getByText(/Scheduling and job tracking are available/i)).toBeVisible()
  await expect(page.getByText(/we don’t yet do scheduling or job tracking/i)).toHaveCount(0)
})

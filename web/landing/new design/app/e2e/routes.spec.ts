import { expect, test } from '@playwright/test'

test('beta pricing surface excludes unavailable features and billing claims', async ({ page }) => {
  await page.goto('/')

  const pricing = page.locator('#pricing')
  await expect(pricing).toBeVisible()
  await expect(pricing).toContainText(/free while we're in beta/i)
  await expect(pricing).toContainText(/future launch/i)
  await expect(pricing).toContainText(/no card or paid subscription/i)

  await expect(pricing).not.toContainText(/Certificates/i)
  await expect(pricing).not.toContainText(/Deposits|partial payments/i)
  await expect(pricing).not.toContainText(/Offline mode|offline operation/i)
  await expect(pricing).not.toContainText(/14 days free|30 days|free trial/i)
  await expect(pricing).not.toContainText(/Paddle/i)
  await expect(pricing).not.toContainText(/Subscribe/i)
  await expect(pricing).toContainText(/Join free beta/i)
})

test('unknown marketing routes show an accessible branded not-found page', async ({ page }) => {
  await page.goto('/this-page-does-not-exist')

  await expect(page).toHaveTitle(/page not found/i)
  await expect(page.getByRole('heading', { level: 1, name: "That page isn't here" })).toBeVisible()
  await expect(page.getByText('404 · Page not found')).toBeVisible()
  await expect(page.getByRole('link', { name: 'Back to home' })).toHaveAttribute('href', '/')
  await expect(page.getByRole('link', { name: 'Read the blog' })).toHaveAttribute('href', '/blog')
  await expect(page.getByRole('link', { name: 'Help & guides' })).toHaveAttribute('href', '/help')
})

const validMarketingPaths = [
  '/',
  '/reset-password',
  '/accept-invite',
  '/subscribe',
  '/quote/route-test-token',
  '/invoice/route-test-token',
  '/pay/route-test-token',
  '/fair-use',
  '/payments/stripe-bounce',
  '/payments/dashboard',
  '/blog',
  '/blog/route-test-post',
  '/help',
  '/help/route-test-guide',
]

for (const path of validMarketingPaths) {
  test(`valid marketing route is not caught by the not-found route: ${path}`, async ({ page }) => {
    await page.route(/\/public\/(quote|invoice)\/[^/?]+(?:\?.*)?$/, (route) =>
      route.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Not found' }),
      }),
    )

    await page.goto(path, { waitUntil: 'domcontentloaded' })

    await expect(page.locator('main')).toBeVisible()
    await expect(
      page.getByRole('heading', { level: 1, name: "That page isn't here" }),
    ).toHaveCount(0)
    await expect(page).toHaveURL(new RegExp(`${path.replaceAll('/', '\\/')}$`))
  })
}

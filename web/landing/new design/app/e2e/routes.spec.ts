import { expect, test } from '@playwright/test'

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

const footerSectionLinks = [
  { name: 'The tour', hash: 'features' },
  { name: 'Pricing', hash: 'pricing' },
  { name: 'Reviews', hash: 'reviews' },
] as const

for (const path of ['/', '/blog', '/blog/ai-in-the-trades', '/help/getting-started']) {
  test(`footer home-section links work from ${path}`, async ({ page }) => {
    await page.goto(path, { waitUntil: 'domcontentloaded' })

    for (const link of footerSectionLinks) {
      await page.goto(path, { waitUntil: 'domcontentloaded' })
      const footerLink = page.locator('footer').getByRole('link', { name: link.name, exact: true })
      await expect(footerLink).toHaveAttribute(
        'href',
        path === '/' ? `#${link.hash}` : `/#${link.hash}`,
      )
      await footerLink.click()

      await expect(page).toHaveURL(new RegExp(`/#${link.hash}$`))
      await expect(page.locator(`#${link.hash}`)).toBeInViewport()
      await expect(page.context().pages()).toHaveLength(1)
    }
  })
}

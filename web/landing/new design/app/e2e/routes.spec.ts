import { expect, test, type Locator, type Page } from '@playwright/test'

test('beta pricing surface excludes unavailable features and billing claims', async ({ page }) => {
  const flagsLoaded = page.waitForResponse(
    (response) => new URL(response.url()).pathname.endsWith('/feature-flags') && response.ok(),
  )
  await page.goto('/')
  await flagsLoaded

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

test('beta pricing surface excludes unavailable features and billing claims', async ({ page }) => {
  const flagsLoaded = page.waitForResponse(
    (response) => new URL(response.url()).pathname.endsWith('/feature-flags') && response.ok(),
  )
  await page.goto('/')
  await flagsLoaded

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

async function expectFullyInViewport(
  page: Page,
  locator: Locator,
) {
  await expect(locator).toBeVisible()
  const box = await locator.boundingBox()
  const viewport = page.viewportSize()
  expect(box).not.toBeNull()
  expect(viewport).not.toBeNull()
  if (!box || !viewport) return
  expect(box.x).toBeGreaterThanOrEqual(-1)
  expect(box.y).toBeGreaterThanOrEqual(-1)
  expect(box.x + box.width).toBeLessThanOrEqual(viewport.width + 1)
  expect(box.y + box.height).toBeLessThanOrEqual(viewport.height + 1)
}

async function expectSingleLine(locator: Locator) {
  const wrapped = await locator.evaluate((el) => {
    const style = window.getComputedStyle(el)
    const parsedLineHeight = Number.parseFloat(style.lineHeight)
    const lineHeight = Number.isFinite(parsedLineHeight) && parsedLineHeight > 0
      ? parsedLineHeight
      : Number.parseFloat(style.fontSize) * 1.2
    return el.getBoundingClientRect().height > lineHeight * 1.5
  })
  expect(wrapped).toBe(false)
}

const responsiveNavCases = [
  { label: 'desktop', viewport: { width: 1440, height: 900 }, expectsPrimaryNav: true },
  { label: 'tablet', viewport: { width: 768, height: 1024 }, expectsPrimaryNav: false },
  { label: 'mobile', viewport: { width: 390, height: 844 }, expectsPrimaryNav: false },
]

for (const { label, viewport, expectsPrimaryNav } of responsiveNavCases) {
  test(`marketing nav is fully usable at ${label} viewport`, async ({ page }) => {
    await page.setViewportSize(viewport)
    await page.goto('/')

    const header = page.locator('header')
    const primaryNav = header.getByRole('navigation', { name: 'Primary' })
    const menuButton = header.getByRole('button', { name: /open menu/i })
    const ctaDesktop = header.getByRole('link', { name: 'Join the beta', exact: true })

    if (expectsPrimaryNav) {
      await expect(primaryNav).toBeVisible()
      await expect(menuButton).toBeHidden()
      await expectFullyInViewport(page, ctaDesktop)

      for (const name of ['Try the AI', 'The tour', 'How it works', 'Pricing', 'Reviews', 'Blog']) {
        const link = primaryNav.getByRole('link', { name, exact: true })
        await expectFullyInViewport(page, link)
        await expectSingleLine(link)
      }
      await expectSingleLine(ctaDesktop)
      return
    }

    await expect(primaryNav).toBeHidden()
    await expect(menuButton).toBeVisible()
    await expectFullyInViewport(page, menuButton)
    await menuButton.click()

    const mobileNav = header.getByRole('navigation', { name: 'Mobile' })
    await expect(mobileNav).toBeVisible()
    await expectFullyInViewport(page, mobileNav)

    for (const name of ['Try the AI', 'The tour', 'How it works', 'Pricing', 'Reviews', 'Blog']) {
      await expectFullyInViewport(page, mobileNav.getByRole('link', { name, exact: true }))
    }
    await expectFullyInViewport(page, mobileNav.getByRole('link', { name: 'Join the beta', exact: true }))
  })
}

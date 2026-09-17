// G21 — Quote view / accept / decline / discuss in the portal: ex-VAT
// subtotal + VAT + total, awaiting-response state, accept with preferred
// dates (staff notified in-app + by email), decline, discuss thread shared
// with the tradie, and pre-review drafts never exposed (C3).
//
// See docs/e2e-coverage-gaps.md row G21.

import { expect, type Page } from "@playwright/test";
import { mailpitConfigured, waitForEmail } from "./mailpit";
import {
  createTenant,
  customerApi,
  exchangeMagicToken,
  extractToken,
  seedSentQuote,
  staffApi,
  stagingConfigured,
  submitIntake,
  uniqueEmail,
  type CustomerSession,
  type Tenant,
  portalTest as test,
} from "./helpers";

let tenant: Tenant;
let customerEmail: string;
let intakeId: string;

async function gotoPortal(page: Page, path = "/"): Promise<void> {
  const joiner = path.includes("?") ? "&" : "?";
  await page.goto(`${path}${joiner}slug=${encodeURIComponent(tenant.slug)}`, {
    waitUntil: "domcontentloaded",
  });
}

/** Seed a sent quote for the shared customer and return a UI session signed
 * in via the quote-ready email's magic link. */
async function seedQuoteAndSignIn(subject: string): Promise<{
  quoteId: string;
  session: CustomerSession;
}> {
  const quote = await seedSentQuote(tenant, {
    title: subject,
    customerEmail,
    quoteRequestId: intakeId,
    lineItems: [
      { description: "New consumer unit", quantity: 1, unit_price: 450 },
      { description: "Labour — half day", quantity: 4, unit_price: 45 },
    ],
  });
  // The quote email subject is fixed ("Your quote from {business}") and does
  // not include the title — match the subject, then disambiguate by title in
  // the body. Mailpit lists newest first, so this is the just-sent quote.
  const mail = await waitForEmail(customerEmail, { subjectIncludes: "Your quote from" });
  expect(mail.text + mail.html).toContain(subject);
  const token = extractToken(mail, "auth/magic");
  const session = await exchangeMagicToken(token);
  return { quoteId: quote.id, session };
}

/** UI sign-in: consume the newest magic-link email already delivered to the
 * shared customer (quote-ready and sign-in emails both carry one). Magic
 * tokens survive exchange, so reuse is fine. */
async function signIn(page: Page): Promise<void> {
  await gotoPortal(page, "/quotes");
  const gate = page.getByText("Sign in to continue");
  // Wait for the portal to settle into its signed-OUT state before deciding a
  // magic link is needed — an immediate isVisible() races the initial data
  // fetch and can wrongly conclude the session is active.
  try {
    await gate.waitFor({ state: "visible", timeout: 45_000 });
  } catch {
    return; // no gate → session already active
  }
  const deadline = Date.now() + 30_000;
  let token: string | null = null;
  while (!token && Date.now() < deadline) {
    const mail = await waitForEmail(customerEmail, { timeoutMs: 3_000 }).catch(() => null);
    if (mail) {
      try {
        token = extractToken(mail, "auth/magic");
      } catch {
        token = null;
      }
    }
  }
  if (!token) throw new Error("no magic link email found for customer");
  await gotoPortal(
    page,
    `/auth/magic?token=${encodeURIComponent(token)}&next=${encodeURIComponent("/quotes")}`,
  );
  await expect(page).toHaveURL(/\/quotes/, { timeout: 45_000 });
  // The gate must be gone — the "Quotes" heading alone renders in both states.
  await expect(gate).toHaveCount(0, { timeout: 45_000 });
}

test.beforeAll(async () => {
  test.skip(!stagingConfigured(), "TEST_API_BASE_URL / TEST_SETUP_TOKEN not set");
  test.skip(!mailpitConfigured(), "MAILPIT_URL / MAILPIT_BASIC_AUTH not set");
  tenant = await createTenant("portal-quotes");
  customerEmail = uniqueEmail("quotes");
  const intake = await submitIntake(tenant, {
    name: "Portal Quotes Customer",
    email: customerEmail,
    description: "Portal quote journeys",
  });
  intakeId = intake.id;
});

test("quote list + detail render ex-VAT totals and hide pre-review drafts (C3)", async ({
  page,
}) => {
  const { quoteId } = await seedQuoteAndSignIn("Awaiting response quote");

  // An unsent DRAFT quote for the same customer must never surface (C3).
  const contacts = await staffApi<Array<Record<string, any>>>(tenant, "/contacts");
  const contactId = contacts.find((c) => c.email === customerEmail)!.id as string;
  await staffApi<{ id: string }>(tenant, "/quotes", {
    method: "POST",
    body: {
      contact_id: contactId,
      title: "SECRET DRAFT — must not leak",
      line_items: [{ description: "Draft line", quantity: 1, unit_price: 999 }],
      vat_rate: 0.2,
    },
  });

  await signIn(page);
  await expect(page.getByText("Awaiting response quote")).toBeVisible();
  await expect(page.getByText("SECRET DRAFT — must not leak")).toHaveCount(0);

  await page.getByText("Awaiting response quote").click();
  await expect(page).toHaveURL(new RegExp(`/quotes/${quoteId}`));
  await expect(page.getByText("Awaiting response", { exact: true })).toBeVisible();
  await expect(page.getByText("New consumer unit")).toBeVisible();
  await expect(page.getByText("Subtotal (ex VAT)")).toBeVisible();
  await expect(page.getByText(/VAT \(20%\)/)).toBeVisible();
  await expect(page.getByText("Total").last()).toBeVisible();
  // 450 + 4×45 = 630 ex VAT; £756 inc VAT.
  await expect(page.getByText("£756.00").first()).toBeVisible();
  await expect(page.getByText(/Sent \d/)).toBeVisible();
});

test("accept with preferred dates → staff notified in-app and by email", async ({ page }) => {
  const { quoteId } = await seedQuoteAndSignIn("Acceptable quote");

  await signIn(page);
  await page.getByText("Acceptable quote").click();
  await page.getByRole("button", { name: "Accept quote" }).click();

  const date = new Date(Date.now() + 4 * 86_400_000).toISOString().slice(0, 10);
  await page.getByLabel("Pick a preferred date").fill(date);
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await page.getByRole("button", { name: "Confirm acceptance" }).click();

  await expect(page.getByText("Booking request sent")).toBeVisible();
  await expect(page.getByText("Awaiting response")).toHaveCount(0);

  // Server-side: quote approved with the reconfirmed dates (G28 surfaces them).
  const quotes = await staffApi<Array<Record<string, any>>>(tenant, "/quotes");
  const quote = quotes.find((q) => q.id === quoteId);
  expect(quote?.status).toBe("approved");
  expect(quote?.accepted_dates).toContain(date);

  // Staff notified in-app…
  const notifications = await staffApi<Array<Record<string, any>>>(tenant, "/notifications");
  const accepted = notifications.find(
    (n) => n.type === "quote_accepted" && (n.body as string).includes("Acceptable quote"),
  );
  expect(accepted, "quote_accepted staff notification").toBeTruthy();
  expect(accepted!.body).toContain(date);

  // …and the customer gets the acceptance email — platform-branded
  // transactional sender (not the tenant's reply-to address).
  const mail = await waitForEmail(customerEmail, { subjectIncludes: "Quote accepted" });
  expect(mail.from).toContain("mytradeportal.co.uk");
  expect(mail.from).not.toContain(tenant.slug);
});

test("decline moves the quote to declined and offers a way back", async ({ page }) => {
  await seedQuoteAndSignIn("Declinable quote");

  await signIn(page);
  await page.getByText("Declinable quote").click();
  await page.getByRole("button", { name: "Decline", exact: true }).click();
  await page.getByRole("button", { name: "Yes, decline" }).click();

  await expect(page.getByText(/You've declined this quote/)).toBeVisible();
  // "Declined" renders three times (status badge, explainer copy, timeline) —
  // assert the status badge specifically.
  await expect(
    page.getByText("Declined", { exact: true }).first(),
  ).toBeVisible();

  const quotes = await staffApi<Array<Record<string, any>>>(tenant, "/quotes");
  expect(quotes.find((q) => q.title === "Declinable quote")?.status).toBe("rejected");
});

/** Seed a quote that is LINKED to a lead (quote.quote_request_id set) and
 * return its id + AI title + lead id. The portal discuss thread only renders
 * for lead-linked quotes (PortalQuoteDetail gates on quote_request_id), and
 * the only API that sets the back-link is the AI generation path —
 * scratch POST /quotes cannot be attached to a lead. */
async function seedLinkedSentQuote(description: string): Promise<{
  quoteId: string;
  title: string;
  quoteRequestId: string;
}> {
  const intake = await submitIntake(tenant, {
    name: "Portal Discuss Customer",
    email: customerEmail,
    description,
  });
  const contacts = await staffApi<Array<Record<string, any>>>(tenant, "/contacts");
  const contactId = contacts.find((c) => c.email === customerEmail)!.id as string;
  const quote = await staffApi<{ id: string }>(tenant, "/quotes/generate", {
    method: "POST",
    body: { contact_id: contactId, description, quote_request_id: intake.id },
  });
  await staffApi(tenant, `/quotes/${quote.id}/send`, { method: "POST" });
  await staffApi(tenant, `/quote-requests/${intake.id}`, {
    method: "PATCH",
    body: { quote_id: quote.id, status: "converted_to_quote" },
  });
  const quotes = await staffApi<Array<{ id: string; title: string }>>(tenant, "/quotes");
  return { quoteId: quote.id, title: quotes.find((q) => q.id === quote.id)!.title, quoteRequestId: intake.id };
}

test("discuss reply lands in the shared staff thread", async ({ page }) => {
  // LLM generation + staging latency push this test close to the default
  // timeout even when everything is healthy.
  test.setTimeout(300_000);
  const { title, quoteRequestId } = await seedLinkedSentQuote(
    "Replace the consumer unit and add surge protection to the circuits",
  );

  await signIn(page);
  await page.getByText(title).click();
  await page.getByRole("button", { name: "Request changes / discuss" }).click();
  const composer = page.locator('[placeholder="Type your reply…"]');
  await composer.fill("Can you swap the consumer unit for a surge-protected one?");
  await composer.press("Enter");
  await expect(page.getByText(/surge-protected one/)).toBeVisible();

  // Staff sees the customer's message on the same thread. The chat UI appends
  // optimistically, so poll the staff API until the POST has landed.
  await expect
    .poll(
      async () => {
        const comms = await staffApi<Array<Record<string, any>>>(
          tenant,
          `/communications?quote_request_id=${quoteRequestId}`,
        );
        return (
          comms.find(
            (c) => c.sender_role === "customer" && (c.body as string)?.includes("surge-protected"),
          ) ?? null
        );
      },
      { timeout: 30_000, intervals: [1_000, 2_000, 5_000] },
    )
    .not.toBeNull();
});

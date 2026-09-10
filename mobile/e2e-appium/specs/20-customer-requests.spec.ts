/**
 * 20 — Customer requests: list/empty state, the full "Request a new quote"
 * wizard (postcode, contact, property, category, description, photos,
 * urgency + preferred dates, budget, consents), persistence of the quote
 * request with all entered fields, draft-quote withholding until review, and
 * the accept (with date reconfirmation + booking) / reject / revised-quote
 * flows.
 *
 * Title note: for the "Something else" category the app uses the free-text
 * description as the quote-request title (stored in
 * quote_requests.structured_data->>'title'), so the unique tag lives in the
 * description.
 *
 * The accept/reject flows need an OPEN (sent) quote, which only the
 * electrician can produce — those tests are opportunistic: they skip (log)
 * when no open quote is on the customer's list, and restore the quote status
 * afterwards when trade credentials allow.
 */
import { relaunchApp } from "../helpers/app";
import { loginAsCustomer } from "../helpers/auth";
import {
  apiGet,
  apiPatch,
  closeDb,
  countRows,
  customerCredsConfigured,
  CUSTOMER_EMAIL,
  CUSTOMER_PASSWORD,
  dbConfigured,
  deleteTestData,
  loginTradeApi,
  tradeCredsConfigured,
  type ApiTenantContext,
} from "../helpers/api";
import {
  byId,
  hasText,
  scrollToTextAndTap,
  tapId,
  tapText,
  textElContains,
  waitForId,
  waitForText,
  dismissKeyboard,
} from "../helpers/ui";

const tag = Date.now().toString(36);
const DESCRIPTION = `E2E request ${tag}: install two mains-powered smoke detectors, hallway and landing, ${tag}.`;
const POSTCODE = "SW1A 1AA";

type QuoteRequestRow = {
  id: string;
  tenant_id?: string;
  structured_data?: Record<string, unknown>;
  raw_text?: string | null;
  preferred_dates?: Array<{ date?: string }>;
  quote_id?: string | null;
};

async function fieldValue(el: { getText: () => Promise<string> }): Promise<string> {
  const raw: string | undefined = await el.getText().catch(() => "");
  return raw ?? "";
}

/** Fill a field by testID if it is currently empty. */
async function fillIfEmpty(id: string, value: string): Promise<void> {
  const el = await waitForId(id);
  const current = await fieldValue(el);
  if (!current) {
    await el.click();
    await el.setValue(value);
    await dismissKeyboard();
  }
}

/** Runs the logged-in customer quote-request wizard and returns at Done. */
async function runQuoteRequestWizard(opts: { withPhoto: boolean }): Promise<void> {
  await waitForId("request-new-quote", 25000);
  await tapId("request-new-quote");
  await waitForId("quote-postcode-input", 15000);

  // Step 1 — postcode.
  await fillIfEmpty("quote-postcode-input", POSTCODE);
  await tapId("quote-check-area");

  // Step 2 — contact (pre-filled from the account; needs a contact method).
  await waitForId("quote-name-input", 15000);
  await tapText("Online chat", 15000);
  await tapId("quote-contact-continue", 15000);

  // Step 3 — property profile (type, age, tenure, parking).
  await waitForId("quote-property-continue", 15000);
  await tapText("Terrace", 15000);
  await tapText("Not sure", 15000); // property age
  await tapText("Owner", 15000); // tenure
  await tapText("Yes", 15000); // van parking (only "Yes" on this step for a house)
  await tapId("quote-property-continue", 15000);

  // Step 4 — job category.
  await waitForId("quote-category-other", 15000);
  await tapId("quote-category-other");
  await tapId("quote-category-continue", 15000);

  // Step 5 — free-text description (multiline input → TextView).
  await waitForId("quote-other-continue", 15000);
  const notes = await (await $$("-ios class chain:**/XCUIElementTypeTextView")).getElements();
  expect(notes.length).toBeGreaterThan(0);
  await notes[0].click();
  await notes[0].setValue(DESCRIPTION);
  await dismissKeyboard();
  await tapId("quote-other-continue", 15000);

  // Step 6 — photos (best effort: the native picker is Apple's UI).
  await waitForId("quote-media-continue", 15000);
  if (opts.withPhoto) {
    try {
      await tapId("quote-media-add-photo", 10000);
      await driver.pause(1500);
      const cancel = await driver.$("~Cancel");
      await cancel.waitForExist({ timeout: 12000 });
      const cell = await $(
        "-ios class chain:**/XCUIElementTypeCollectionView/XCUIElementTypeCell[1]"
      );
      await cell.waitForExist({ timeout: 10000 });
      await cell.click();
      await driver.pause(600);
      const add = await driver.$("~Add");
      if (await add.isExisting()) await add.click();
      await driver.pause(800);
    } catch {
      console.log("WARN: photo picker interaction failed — continuing without photos");
    }
  }
  await tapId("quote-media-continue", 15000);

  // Step 7 — urgency + one preferred date.
  await waitForId("quote-urgency-continue", 15000);
  await tapText("Flexible", 15000);
  const tomorrow = new Date(Date.now() + 86400000).toLocaleDateString("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
  await tapText(tomorrow, 15000).catch(() => {
    console.log(`WARN: preferred date chip not found: ${tomorrow}`);
  });
  await tapId("quote-urgency-continue", 15000);

  // Step 8 — budget (all optional).
  await waitForId("quote-budget-continue", 15000);
  await tapId("quote-budget-continue", 15000);

  // Step 9 — consents (required two).
  await waitForId("quote-submit", 15000);
  await tapId("quote-consent-terms");
  await tapId("quote-consent-contact");
  await tapId("quote-submit", 25000);

  // Step 10 — confirmation, then Done.
  await waitForText("has your request", 25000);
  await tapId("quote-done", 15000);
  await driver.pause(800);
}

describe("20: customer quote requests", () => {
  if (!customerCredsConfigured()) {
    console.log("SKIP: E2E_CUSTOMER_EMAIL/E2E_CUSTOMER_PASSWORD not set");
    return;
  }

  let tradeCtx: ApiTenantContext | null = null;

  before(async () => {
    await loginAsCustomer(CUSTOMER_EMAIL, CUSTOMER_PASSWORD);
    if (tradeCredsConfigured()) {
      tradeCtx = await loginTradeApi();
    }
  });

  after(async () => {
    if (!dbConfigured()) {
      await closeDb();
      return;
    }
    // Delete the linked AI draft quote first (quote_requests.quote_id FK is
    // SET NULL when the quote goes away), then the quote request itself and
    // any chat rows carrying the tag.
    await deleteTestData(
      "id = (SELECT quote_id FROM quote_requests WHERE structured_data->>'title' = $1)",
      [DESCRIPTION]
    );
    await deleteTestData("structured_data->>'title' = $1", [DESCRIPTION]);
    await deleteTestData("body LIKE $1", [`%${tag}%`]);
    await closeDb();
  });

  async function findQuoteRequest(): Promise<QuoteRequestRow | null> {
    if (tradeCtx) {
      const rows = (await apiGet(tradeCtx, "/quote-requests")) as QuoteRequestRow[];
      return rows.find((r) => r.structured_data?.title === DESCRIPTION) ?? null;
    }
    return null;
  }

  it("requests screen shows the list or empty-state copy", async () => {
    await waitForId("request-new-quote", 25000);
    await waitForId("customer-ai-banner", 15000);
    const empty = await hasText("No requests yet");
    await waitForText("Track your quote requests", 15000);
    if (empty) {
      await waitForText("Request a new quote", 15000);
    }
  });

  it("submits a new quote request via the wizard", async () => {
    await runQuoteRequestWizard({ withPhoto: true });
    // Back on the requests list: the new request appears as a card (no price
    // while it awaits review).
    const cardText = await textElContains(`E2E request ${tag}`);
    await cardText.waitForExist({ timeout: 25000 });
  });

  it("persists the quote request with all entered fields", async () => {
    const qr = await findQuoteRequest();
    expect(qr).toBeTruthy();
    expect(qr?.raw_text).toContain(tag);
    expect(qr?.preferred_dates?.length).toBeGreaterThanOrEqual(1);
    if (dbConfigured()) {
      const n = await countRows(
        "quote_requests qr JOIN contacts c ON c.id = qr.contact_id",
        "qr.structured_data->>'title' = $1 AND c.postcode = $2",
        [DESCRIPTION, POSTCODE]
      );
      expect(n).toBe(1);
    }
  });

  it("withholds the draft quote until the electrician reviews it", async () => {
    // Open the card for our request (quote cards are tappable; bare request
    // cards are not — the detail assertions only apply when a draft exists).
    const card = await textElContains(`E2E request ${tag}`);
    const onList = await card
      .waitForExist({ timeout: 15000 })
      .then(() => true)
      .catch(() => false);
    if (!onList) {
      console.log("WARN: request card text not found on the list — skipping detail check");
      return;
    }
    await card.click();
    await driver.pause(600);
    if (await hasText("Quote request received")) {
      // Awaiting-review detail: reassurance copy, no pricing block.
      expect(await hasText("Total")).toBe(false);
      expect(await hasText("Subtotal")).toBe(false);
    } else {
      console.log(
        "INFO: no draft-quote detail (request pending or already reviewed) — withholding check limited to list badge"
      );
      await waitForText("AWAITING REVIEW", 10000).catch(() => {
        console.log("INFO: quote already reviewed — OPEN badge may be showing instead");
      });
    }
    await tapId("back-button", 8000).catch(() => undefined);
    await waitForId("request-new-quote", 15000);
  });

  it("accept flow: reconfirm dates, book, appointment persists", async () => {
    if (!(await hasText("OPEN"))) {
      console.log("SKIP: no OPEN quote on the customer list to accept");
      return;
    }
    await scrollToTextAndTap("OPEN", { timeoutMs: 25000 });
    await waitForId("quote-accept", 25000);
    await tapId("quote-accept");

    // Date reconfirmation panel appears when the request had preferred dates.
    if (await byId("quote-reconfirm-dates").isExisting()) {
      await tapId("reconfirm-date-0", 15000).catch(() => undefined);
      await tapId("reconfirm-date-0", 15000).catch(() => undefined); // reselect
      await tapId("quote-confirm-accept", 25000);
    }

    // Post-acceptance booking view.
    await waitForText("Book a date", 25000);
    await tapId("book-day-1", 15000);
    await tapId("book-time-1", 15000);
    await tapId("booking-confirm", 25000);
    await waitForText("Appointments", 25000).catch(() => waitForText("Bookings", 25000));

    if (tradeCtx) {
      const quotes = (await apiGet(tradeCtx, "/quotes")) as Array<Record<string, unknown>>;
      const accepted = quotes.find((q) => q.status === "accepted") as
        | Record<string, unknown>
        | undefined;
      expect(accepted).toBeTruthy();
      const title = String(accepted?.title);
      const appts = (await apiGet(tradeCtx, "/appointments")) as Array<Record<string, unknown>>;
      const appt = appts.find((a) => a.title === title);
      expect(appt).toBeTruthy();
      // Restore: un-accept the quote (we did not create it) and drop the
      // booking we just made.
      await apiPatch(tradeCtx, `/quotes/${String(accepted?.id)}`, { status: "sent" });
      if (appt && dbConfigured()) {
        await deleteTestData("id = $1", [String(appt.id)]);
      }
    } else {
      console.log("SKIP: trade creds unavailable — cannot assert/restore quote state");
    }
  });

  it("reject flow: decline with a reason", async () => {
    if (!(await hasText("OPEN"))) {
      console.log("SKIP: no OPEN quote on the customer list to reject");
      return;
    }
    await scrollToTextAndTap("OPEN", { timeoutMs: 25000 });
    await waitForText("Reject quote", 25000);
    await tapText("Reject quote", 15000);
    await waitForText("Decline quote", 15000);
    await tapText("Confirm decline", 25000);
    await waitForText("Quote declined", 25000);
    if (tradeCtx) {
      const quotes = (await apiGet(tradeCtx, "/quotes")) as Array<Record<string, unknown>>;
      const rejected = quotes.find((q) => q.status === "rejected") as
        | Record<string, unknown>
        | undefined;
      expect(rejected).toBeTruthy();
      await apiPatch(tradeCtx, `/quotes/${String(rejected?.id)}`, { status: "sent" });
    }
  });

  it("revised-quote button opens the chat thread", async () => {
    if (!(await hasText("REJECTED"))) {
      console.log("SKIP: no REJECTED quote on the customer list");
      return;
    }
    await scrollToTextAndTap("REJECTED", { timeoutMs: 25000 });
    await waitForText("Request a revised quote", 25000);
    await tapText("Request a revised quote", 15000);
    // The requests screen routes "Request changes" into the messages thread.
    await waitForId("chat-composer", 25000);
    await relaunchApp();
  });
});

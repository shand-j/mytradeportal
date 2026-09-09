/**
 * Trade leads (manual quote requests):
 *  - manual-lead entry creates a lead + CRM contact, all fields persisted
 *  - lead detail renders the captured data and the unregistered-account state
 *  - lead → AI quote conversion via the quote intake screen
 *
 * The manual-lead form only exposes testIDs for the email field and submit;
 * the message (multiline TextView) and name/phone/postcode (single-line
 * TextFields) are located by element type / placeholderValue.
 */
import {
  apiGet,
  closeDb,
  countRows,
  dbConfigured,
  deleteTestData,
  findContactByEmail,
  loginTradeApi,
  tradeCredsConfigured,
  TRADE_EMAIL,
  TRADE_PASSWORD,
  type ApiTenantContext,
} from "../helpers/api";
import { loginAsTrade } from "../helpers/auth";
import {
  byId,
  swipeUp,
  tapId,
  tapText,
  waitForId,
  waitForText,
} from "../helpers/ui";
import { API_BASE } from "../helpers/env";

const TAG = Date.now().toString(36);
const CUSTOMER_NAME = `E2E Lead Contact ${TAG}`;
const CUSTOMER_EMAIL = `e2e-lead-${TAG}@example.com`;
const CUSTOMER_PHONE = "07987654321";
const CUSTOMER_POSTCODE = "AB1 2CD";
const LEAD_MESSAGE = `E2E lead ${TAG}: customer needs a consumer unit replaced in a 3-bed semi. Please call to arrange a survey.`;

interface ApiContactRow {
  id: string;
  email: string | null;
}

interface ApiQuoteRequestRow {
  id: string;
  raw_text: string | null;
  status: string;
  customer_id: string | null;
  quote: { id: string; line_items: unknown[] } | null;
}

async function apiPost(
  ctx: ApiTenantContext,
  path: string,
  payload?: Record<string, unknown>
): Promise<unknown> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${ctx.token}`,
      "X-Tenant-ID": ctx.tenantId,
      "Content-Type": "application/json",
    },
    body: payload === undefined ? undefined : JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`POST ${path} failed: ${res.status} ${await res.text()}`);
  return res.json();
}

/** Swipe up until the testID exists. */
async function scrollUntilId(id: string, timeoutMs = 20000) {
  const el = byId(id);
  const start = Date.now();
  while (!(await el.isExisting())) {
    if (Date.now() - start > timeoutMs) {
      throw new Error(`scrollUntilId timed out looking for testID: ${id}`);
    }
    await swipeUp();
    await driver.pause(350);
  }
  return el;
}

/** Single-line TextField located by its placeholder (RN forwards it as placeholderValue). */
function inputByPlaceholder(placeholder: string) {
  const escaped = placeholder.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
  return $(`-ios predicate string:placeholderValue == "${escaped}"`);
}

/** The manual-lead message box is the only multiline TextView on the screen. */
function messageTextView() {
  return $(`-ios class chain:**/XCUIElementTypeTextView`);
}

type SettableElement = { click(): Promise<unknown>; setValue(value: string): Promise<unknown> };

async function setValue(el: SettableElement, value: string) {
  await el.click();
  await el.setValue(value);
  await driver.hideKeyboard().catch(() => undefined);
}

describe("trade leads", () => {
  if (!tradeCredsConfigured()) {
    console.log("SKIP: E2E_TRADE_EMAIL/E2E_TRADE_PASSWORD not set");
    return;
  }

  let ctx: ApiTenantContext;
  let contactId = "";
  let leadId = "";
  let generatedQuoteId = "";

  before(async () => {
    ctx = await loginTradeApi();
    await loginAsTrade(TRADE_EMAIL, TRADE_PASSWORD);
  });

  after(async () => {
    if (!dbConfigured()) {
      console.log("NOTE: MTP_DB_URL not set — skipping DB cleanup for", CUSTOMER_EMAIL);
      await closeDb();
      return;
    }
    try {
      if (leadId) {
        await deleteTestData("quote_request_id = $1", [leadId]);
        await deleteTestData("id = $1", [leadId]);
      }
      if (generatedQuoteId) {
        await deleteTestData("quote_id = $1", [generatedQuoteId]);
        await deleteTestData("id = $1", [generatedQuoteId]);
      }
      if (contactId) {
        await deleteTestData("contact_id = $1", [contactId]);
        await deleteTestData("email = $1", [CUSTOMER_EMAIL]);
        await deleteTestData("id = $1", [contactId]);
      }
    } finally {
      await closeDb();
    }
  });

  it("manual lead entry creates a persisted lead and contact", async () => {
    await tapId("tab-dashboard");
    await waitForText("Dashboard");
    await tapText("+ New lead");
    await waitForText("Manual lead entry");

    await setValue(await messageTextView(), LEAD_MESSAGE);
    await tapText("Phone");
    await setValue(await inputByPlaceholder("Name"), CUSTOMER_NAME);
    await setValue(await inputByPlaceholder("Phone"), CUSTOMER_PHONE);
    await setValue(await waitForId("manual-lead-email"), CUSTOMER_EMAIL);
    await setValue(await inputByPlaceholder("Postcode"), CUSTOMER_POSTCODE);

    await tapId("manual-lead-submit");
    await waitForText("Lead saved — opening it now…", 25000);
    await waitForText("Lead detail", 25000);

    // The created lead opens straight away; its id comes from the API.
    const leads = (await apiGet(ctx, "/quote-requests")) as ApiQuoteRequestRow[];
    const lead = leads.find((l) => l.raw_text === LEAD_MESSAGE);
    expect(lead).toBeTruthy();
    if (lead) leadId = lead.id;

    if (dbConfigured()) {
      const contact = await findContactByEmail(CUSTOMER_EMAIL);
      expect(contact).toBeTruthy();
      if (contact) {
        contactId = String(contact.id);
        expect(contact.name).toBe(CUSTOMER_NAME);
        expect(contact.phone).toBe(CUSTOMER_PHONE);
        expect(String(contact.postcode).toUpperCase()).toBe(CUSTOMER_POSTCODE);
      }
      const leadsInDb = await countRows("quote_requests", "raw_text = $1", [LEAD_MESSAGE]);
      expect(leadsInDb).toBe(1);
    }
  });

  it("lead detail renders the captured data and unregistered-account state", async () => {
    await waitForText(CUSTOMER_NAME);
    await waitForText(CUSTOMER_PHONE);
    await waitForText(CUSTOMER_EMAIL);
    await waitForText("Manual");
    await waitForText("This week");
    await waitForText(CUSTOMER_POSTCODE.toUpperCase());

    // No customer app account is linked: invite is offered, chat is not.
    await waitForId("lead-invite-to-app");
    expect(await byId("lead-open-chat").isExisting()).toBe(false);

    const api = (await apiGet(ctx, `/quote-requests/${leadId}`)) as ApiQuoteRequestRow;
    expect(api.customer_id).toBeNull();
  });

  it("lead converts to an AI-generated quote via the intake screen", async () => {
    await tapId("lead-generate-quote");
    await waitForText("Quote intake");
    await waitForText(CUSTOMER_NAME);

    await tapId("intake-generate-quote");
    // Async generation: the quotes list shows the progress banner.
    await waitForId("quote-generating-banner", 25000);

    // Poll the backend until the generation job attaches a quote to the lead.
    const deadline = Date.now() + 150000;
    let quoteId: string | null = null;
    while (Date.now() < deadline) {
      const lead = (await apiGet(ctx, `/quote-requests/${leadId}`)) as ApiQuoteRequestRow;
      if (lead.quote) {
        quoteId = lead.quote.id;
        break;
      }
      await driver.pause(3000);
    }
    expect(quoteId).toBeTruthy();
    if (!quoteId) return;
    generatedQuoteId = quoteId;

    // The ready banner replaces the generating one; tapping opens the quote.
    await waitForId("quote-ready-banner", 60000);
    await tapId("quote-ready-banner");
    await waitForText("Review quote", 25000);

    const quote = (await apiGet(ctx, `/quotes/${quoteId}`)) as {
      status: string;
      line_items: unknown[];
      quote_request_id: string | null;
    };
    expect(quote.quote_request_id).toBe(leadId);
    expect(quote.line_items.length).toBeGreaterThanOrEqual(1);
  });
});

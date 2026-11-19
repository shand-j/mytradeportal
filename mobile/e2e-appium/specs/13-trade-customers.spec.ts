/**
 * Trade customers (CRM contacts):
 *  - customers list renders search + new-customer entry
 *  - creating a customer (via the "New Customer" → manual-lead flow) persists
 *    name/phone/email/postcode; the address field has no UI input anywhere in
 *    the trade app, so it is set through the supported PATCH /contacts endpoint
 *    and then asserted together with the UI-entered fields
 *  - the CRM contact card expands to show the persisted details
 *  - an unregistered customer (no app account) is offered "Invite to app" on
 *    their lead instead of "Open chat" (the app's account-state signal)
 */
import {
  apiGet,
  apiPatch,
  closeDb,
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
import { relaunchApp } from "../helpers/app";
import {
  byId,
  swipeUp,
  tapId,
  textElContains,
  waitForId,
  waitForText,
  dismissKeyboard,
} from "../helpers/ui";
import { API_BASE } from "../helpers/env";

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

const TAG = Date.now().toString(36);
const CUSTOMER_NAME = `E2E Customer ${TAG}`;
const CUSTOMER_EMAIL = `e2e-customer-${TAG}@example.com`;
const CUSTOMER_PHONE = "07700900123";
const CUSTOMER_POSTCODE = "M1 2AB";
const CUSTOMER_ADDRESS = `Flat ${TAG.toUpperCase()}, 1 E2E Road, Testtown`;
const LEAD_MESSAGE = `E2E customer ${TAG}: asked for a quote to install two outdoor sockets and an exterior light.`;

interface ApiContactRow {
  id: string;
  name: string;
  email: string | null;
  phone: string | null;
  address: string | null;
  postcode: string | null;
}

interface ApiQuoteRequestRow {
  id: string;
  raw_text: string | null;
  customer_id: string | null;
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

function inputByPlaceholder(placeholder: string) {
  const escaped = placeholder.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
  return $(`-ios predicate string:placeholderValue == "${escaped}"`);
}

function messageTextView() {
  return $(`-ios class chain:**/XCUIElementTypeTextView`);
}

type SettableElement = { click(): Promise<unknown>; setValue(value: string): Promise<unknown> };

async function setValue(el: SettableElement, value: string) {
  await el.click();
  await el.setValue(value);
  await dismissKeyboard();
}

describe("trade customers", () => {
  if (!tradeCredsConfigured()) {
    console.log("SKIP: E2E_TRADE_EMAIL/E2E_TRADE_PASSWORD not set");
    return;
  }

  let ctx: ApiTenantContext;
  let contactId = "";
  let leadId = "";

  afterEach(async function () {
    const state = (this as { currentTest?: { state?: string } }).currentTest?.state;
    if (state !== "failed") return;
    const fs = await import("node:fs");
    try {
      const num = 13;
      fs.writeFileSync(`/tmp/e2e-debug-${num}-${Date.now()}.xml`, await driver.getPageSource());
    } catch {
      /* keep the original error */
    }
  });

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
      if (contactId) {
        await deleteTestData("contact_id = $1", [contactId]);
        await deleteTestData("email = $1", [CUSTOMER_EMAIL]);
        await deleteTestData("id = $1", [contactId]);
      }
    } finally {
      await closeDb();
    }
  });

  it("customers list renders search and the new-customer entry", async () => {
    await tapId("tab-customers");
    await waitForText("Customers");
    await waitForText("Search contacts, view history, and add notes.");
    await waitForId("customers-search");
    await waitForId("customers-new-customer");
  });

  it("creates a customer with a unique email and persists all fields", async () => {
    await tapId("customers-new-customer");
    await waitForText("Add New Customer");

    // No job details: the form's only action is "Save customer", which
    // creates the contact and lands on its detail screen. (With 30+ chars of
    // job details a "Generate AI quote" action appears instead — that lead
    // path is covered by 12-trade-leads.)
    await setValue(await inputByPlaceholder("Name"), CUSTOMER_NAME);
    await setValue(await inputByPlaceholder("Phone"), CUSTOMER_PHONE);
    await setValue(await waitForId("manual-lead-email"), CUSTOMER_EMAIL);
    await setValue(await inputByPlaceholder("Postcode"), CUSTOMER_POSTCODE);

    await tapId("manual-lead-submit");
    await waitForText("Customer", 25000);

    const contacts = (await apiGet(ctx, "/contacts")) as ApiContactRow[];
    const created = contacts.find((c) => c.email === CUSTOMER_EMAIL);
    expect(created).toBeTruthy();
    if (!created) return;
    contactId = created.id;

    // No trade-UI input exists for the address field; set it through the
    // supported contact update endpoint, then assert everything together.
    await apiPatch(ctx, `/contacts/${contactId}`, { address: CUSTOMER_ADDRESS });

    if (dbConfigured()) {
      const contact = await findContactByEmail(CUSTOMER_EMAIL);
      expect(contact).toBeTruthy();
      if (contact) {
        expect(contact.name).toBe(CUSTOMER_NAME);
        expect(contact.phone).toBe(CUSTOMER_PHONE);
        expect(contact.address).toBe(CUSTOMER_ADDRESS);
        expect(String(contact.postcode).toUpperCase()).toBe(CUSTOMER_POSTCODE);
      }
    }
  });

  it("contact card expands to show the persisted details and a create-quote action", async () => {
    // The address was set via API in the previous test; the contacts query
    // caches for 30s+ — restart the app so the list refetches with it.
    await relaunchApp();
    await tapId("tab-customers");
    await waitForText("Customers");
    await scrollUntilId(`contact-card-${contactId}`);
    await tapId(`contact-card-${contactId}`);
    // The whole card collapses into one accessible element; expanded details
    // (address, "Customer since …") are substrings of its composite label.
    const card = await waitForId(`contact-card-${contactId}`);
    const label = String(await card.getAttribute("label"));
    expect(label).toContain("Customer since");
    expect(label).toContain(CUSTOMER_ADDRESS);
    await waitForId(`contact-create-quote-${contactId}`);
  });

  it("unregistered customer is offered the app invite instead of chat", async () => {
    // The save-customer flow creates no lead; create one via API (the
    // web-form/QR path in production) so the invite-vs-chat state renders.
    const lead = (await apiPost(ctx, "/quote-requests", {
      contact_id: contactId,
      source: "manual",
      raw_text: LEAD_MESSAGE,
      urgency: "this_week",
    })) as ApiQuoteRequestRow;
    leadId = lead.id;
    const api = (await apiGet(ctx, `/quote-requests/${leadId}`)) as ApiQuoteRequestRow;
    expect(api.customer_id).toBeNull();

    // The lead was created behind the app's back; relaunch so the quotes
    // list refetches rather than serving its stale React Query cache.
    await relaunchApp();
    await tapId("tab-quotes");
    await waitForText("Quotes");
    await scrollUntilId(`lead-card-${leadId}`);
    await tapId(`lead-card-${leadId}`);
    await waitForText("Lead detail");
    await waitForText(CUSTOMER_NAME);
    await waitForId("lead-invite-to-app");
    expect(await byId("lead-open-chat").isExisting()).toBe(false);
  });
});

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
import { relaunchApp } from "../helpers/app";
import {
  byId,
  dismissKeyboard,
  swipeUp,
  tapId,
  tapText,
  textElContains,
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
  customer: { id: string } | null;
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

type SettableElement = {
  click(): Promise<unknown>;
  setValue(value: string): Promise<unknown>;
  getAttribute(name: string): Promise<unknown>;
};

/** Click → type → read back, so misdirected focus fails loudly here, not later. */
async function setValue(el: SettableElement, value: string, defocusLabel?: string) {
  // A tap on the next field while the keyboard is up just dismisses the
  // keyboard (RN default) and typing continues in the previous field —
  // always dismiss first. Single-line fields: Return works. Multiline
  // fields would swallow Return as a newline — defocus via a label tap.
  await dismissKeyboard();
  await el.click();
  await el.setValue(value);
  await driver.pause(300);
  const actual = String((await el.getAttribute("value")) ?? "");
  if (!actual.includes(value)) {
    throw new Error(`field read-back mismatch: typed "${value}" but field holds "${actual}"`);
  }
  if (defocusLabel) {
    await tapText(defocusLabel);
  } else {
    await dismissKeyboard();
  }
}

describe("trade leads", () => {
  if (!tradeCredsConfigured()) {
    console.log("SKIP: E2E_TRADE_EMAIL/E2E_TRADE_PASSWORD not set");
    return;
  }

  afterEach(async function () {
    const state = (this as { currentTest?: { state?: string } }).currentTest?.state;
    if (state !== "failed") return;
    const fs = await import("node:fs");
    try {
      fs.writeFileSync(`/tmp/e2e-debug-12-${Date.now()}.xml`, await driver.getPageSource());
    } catch {
      /* keep the original error */
    }
  });

  let ctx: ApiTenantContext;
  let contactId = "";
  let leadId = "";
  let secondLeadId = "";
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
      if (secondLeadId) {
        await deleteTestData("quote_request_id = $1", [secondLeadId]);
        await deleteTestData("id = $1", [secondLeadId]);
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
    await tapId("tab-customers");
    await waitForId("customers-new-customer");
    await tapId("customers-new-customer");
    await waitForText("Add New Customer");

    await setValue(await messageTextView(), LEAD_MESSAGE, "Urgency");
    await tapText("Phone");
    await setValue(await inputByPlaceholder("Name"), CUSTOMER_NAME);
    await setValue(await inputByPlaceholder("Phone"), CUSTOMER_PHONE);
    await setValue(await waitForId("manual-lead-email"), CUSTOMER_EMAIL);
    await setValue(await inputByPlaceholder("Postcode"), CUSTOMER_POSTCODE);

    // With job details of 30+ chars the primary action is "Generate AI
    // quote": it saves the contact, creates the lead, kicks off generation
    // and lands on the quotes list showing the progress banner.
    await tapId("manual-lead-generate-quote");
    await waitForId("quote-generating-banner", 30000);

    // The created lead opens straight away; its id comes from the API.
    const leads = (await apiGet(ctx, "/quote-requests")) as ApiQuoteRequestRow[];
    const lead = leads.find((l) => l.raw_text === LEAD_MESSAGE);
    expect(lead).toBeTruthy();
    if (lead) {
      leadId = lead.id;
      // The lead payload carries the CRM contact — the DB lookup below is a
      // cross-check, not the source (MTP_DB_URL is optional).
      contactId = lead.customer?.id ?? contactId;
    }
    expect(contactId).toBeTruthy();

    if (dbConfigured()) {
      const contact = await findContactByEmail(CUSTOMER_EMAIL);
      expect(contact).toBeTruthy();
      if (contact) {
        expect(String(contact.id)).toBe(contactId);
        expect(contact.name).toBe(CUSTOMER_NAME);
        expect(contact.phone).toBe(CUSTOMER_PHONE);
        expect(String(contact.postcode).toUpperCase()).toBe(CUSTOMER_POSTCODE);
      }
      const leadsInDb = await countRows("quote_requests", "raw_text = $1", [LEAD_MESSAGE]);
      expect(leadsInDb).toBe(1);
    }
  });

  it("lead detail renders the captured data and unregistered-account state", async () => {
    // The create flow lands on the quotes list; open the lead from its card.
    await waitForId(`lead-card-${leadId}`, 20000);
    await tapId(`lead-card-${leadId}`);
    await waitForText("Lead detail", 25000);
    await waitForText(CUSTOMER_NAME);
    await waitForText(CUSTOMER_PHONE);
    await waitForText(CUSTOMER_EMAIL);
    // Source/postcode/urgency render as one composite line:
    // "Manual · AB1 2CD · This week".
    const meta = await textElContains("Manual ·");
    expect(String(await meta.getAttribute("label"))).toContain(CUSTOMER_POSTCODE.toUpperCase());
    expect(String(await meta.getAttribute("label"))).toContain("This week");

    // No customer app account is linked: invite is offered, chat is not.
    await waitForId("lead-invite-to-app");
    expect(await byId("lead-open-chat").isExisting()).toBe(false);

    const api = (await apiGet(ctx, `/quote-requests/${leadId}`)) as ApiQuoteRequestRow;
    expect(api.customer_id).toBeNull();
  });

  it("lead converts to an AI-generated quote via the intake screen", async () => {
    // Lead #1 already has a quote (creation kicks generation off), so the
    // intake conversion is exercised on a SECOND, quoteless lead — the
    // web-form/QR path in production. Created via API to keep the UI steps
    // focused on the conversion itself.
    const second = (await apiPost(ctx, "/quote-requests", {
      contact_id: contactId,
      source: "manual",
      raw_text: `E2E lead ${TAG} follow-up: add two outside sockets to the patio wall.`,
      urgency: "this_week",
    })) as ApiQuoteRequestRow;
    secondLeadId = second.id;

    // The second lead was created behind the app's back; the mounted quotes
    // screen holds a stale React Query cache and never renders the new card
    // (same class as spec 11's request-info fix). Relaunch to force a fresh
    // fetch — the session token survives relaunch.
    await relaunchApp();
    await tapId("tab-quotes");
    await waitForText("Quotes");
    await scrollUntilId(`lead-card-${secondLeadId}`);
    await tapId(`lead-card-${secondLeadId}`);
    await waitForText("Lead detail", 25000);
    await tapId("lead-generate-quote");
    await waitForText("Quote intake");
    // Contact line renders as a composite: "Name · POSTCODE · Urgency".
    const who = textElContains(CUSTOMER_NAME);
    await who.waitForExist({ timeout: 15000 });
    expect(String(await who.getAttribute("label"))).toContain(CUSTOMER_NAME);

    await tapId("intake-generate-quote");
    // Async generation: the quotes list shows the progress banner.
    await waitForId("quote-generating-banner", 25000);

    // Poll the backend until the generation job attaches a quote to the lead.
    const deadline = Date.now() + 150000;
    let quoteId: string | null = null;
    while (Date.now() < deadline) {
      const lead = (await apiGet(ctx, `/quote-requests/${secondLeadId}`)) as ApiQuoteRequestRow;
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
    expect(quote.quote_request_id).toBe(secondLeadId);
    expect(quote.line_items.length).toBeGreaterThanOrEqual(1);
  });
});

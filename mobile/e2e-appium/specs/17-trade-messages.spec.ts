/**
 * 17 — Trade messages: inbox list, open a lead thread, send a message as the
 * business, and assert it persisted in the communications table with
 * direction "outbound" (business) — customer-authored rows are "inbound".
 *
 * The thread must belong to a chat-reachable customer: for account-less
 * contacts the app replaces the composer with the phone/email contact card
 * (customerReachable === false), so the spec creates its own lead on the
 * registered E2E customer's CRM contact via the API.
 */
import { loginAsTrade } from "../helpers/auth";
import { relaunchApp } from "../helpers/app";
import {
  apiGet,
  closeDb,
  countRows,
  CUSTOMER_EMAIL,
  customerCredsConfigured,
  dbConfigured,
  deleteTestData,
  loginTradeApi,
  tradeCredsConfigured,
  TRADE_EMAIL,
  TRADE_PASSWORD,
  type ApiTenantContext,
} from "../helpers/api";
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

const tag = Date.now().toString(36);
const MESSAGE = `E2E business reply ${tag} - we can attend this week.`;
const LEAD_TEXT = `E2E inbox lead ${tag}: consumer unit keeps tripping, need a visit.`;

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

/** First element whose accessibility id starts with the given prefix. */
async function firstByIdPrefix(
  prefix: string
): Promise<WebdriverIO.Element | null> {
  const els = await (await $$(`-ios predicate string:name BEGINSWITH '${prefix}'`)).getElements();
  return els.length > 0 ? els[0] : null;
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

describe("17: trade messages (inbox + chat thread)", () => {
  if (!tradeCredsConfigured()) {
    console.log("SKIP: E2E_TRADE_EMAIL/E2E_TRADE_PASSWORD not set");
    return;
  }

  let messageSent = false;
  let leadId = "";

  before(async () => {
    await loginAsTrade(TRADE_EMAIL, TRADE_PASSWORD);

    if (customerCredsConfigured()) {
      const ctx = await loginTradeApi();
      const contacts = (await apiGet(ctx, "/contacts")) as Array<{
        id: string;
        email: string | null;
      }>;
      const reachable = contacts.find((c) => c.email === CUSTOMER_EMAIL);
      if (!reachable) {
        console.log(`NOTE: no CRM contact for ${CUSTOMER_EMAIL} — thread tests will skip`);
        return;
      }
      const lead = (await apiPost(ctx, "/quote-requests", {
        contact_id: reachable.id,
        source: "manual",
        raw_text: LEAD_TEXT,
        urgency: "this_week",
      })) as { id: string };
      leadId = lead.id;
      // The lead was created behind the app's back; a relaunch forces the
      // inbox to refetch (the session token survives relaunch).
      await relaunchApp();
    }
  });

  after(async () => {
    if (messageSent && dbConfigured()) {
      // `body` only exists on communications/notifications; other scoped
      // tables fail silently in deleteTestData.
      await deleteTestData("body = $1", [MESSAGE]);
    }
    if (leadId && dbConfigured()) {
      await deleteTestData("quote_request_id = $1", [leadId]);
      await deleteTestData("id = $1", [leadId]);
    }
    await closeDb();
  });

  it("renders the inbox (list or empty state)", async () => {
    await tapId("tab-messages");
    await waitForText("Messages");
    // Empty state renders as one composite line:
    // "No conversations yet — new quote requests will appear here."
    const empty = await textElContains("No conversations yet").isExisting();
    const hasLead = (await firstByIdPrefix("inbox-lead-")) !== null;
    expect(empty || hasLead).toBe(true);
    if (empty) {
      console.log("SKIP: inbox is empty — no lead threads to open");
    }
  });

  it("opens a lead thread", async () => {
    if (!leadId) {
      console.log("SKIP: no reachable lead thread available");
      return;
    }
    await scrollUntilId(`inbox-lead-${leadId}`);
    await tapId(`inbox-lead-${leadId}`);
    await waitForText("Messages", 15000);
    await waitForId("chat-composer", 15000);
    await tapId("back-button", 8000).catch(() => undefined);
    await waitForText("Messages", 15000);
  });

  it("sends a message as the business and persists it outbound", async () => {
    if (!leadId) {
      console.log("SKIP: no reachable lead thread available");
      return;
    }
    await scrollUntilId(`inbox-lead-${leadId}`);
    await tapId(`inbox-lead-${leadId}`);
    const composer = await waitForId("chat-composer", 15000);
    await composer.click();
    await composer.setValue(MESSAGE);
    await dismissKeyboard();
    await tapId("chat-send", 25000);
    // The bubble renders our text in the thread.
    await waitForText(MESSAGE, 25000);
    messageSent = true;

    if (dbConfigured()) {
      const n = await countRows(
        "communications",
        "body = $1 AND sender_role = 'business' AND direction = 'outbound'",
        [MESSAGE]
      );
      expect(n).toBe(1);
      // Direction semantics: at least one customer-authored inbound row may
      // exist in the thread history; our own row must never be inbound.
      const inbound = await countRows(
        "communications",
        "body = $1 AND direction = 'inbound'",
        [MESSAGE]
      );
      expect(inbound).toBe(0);
    } else {
      console.log("SKIP: MTP_DB_URL not set — DB persistence assertion skipped");
    }
  });
});

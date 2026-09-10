/**
 * 17 — Trade messages: inbox list, open the first lead thread, send a message
 * as the business, and assert it persisted in the communications table with
 * direction "outbound" (business) — customer-authored rows are "inbound".
 */
import { loginAsTrade } from "../helpers/auth";
import {
  closeDb,
  countRows,
  dbConfigured,
  deleteTestData,
  loginTradeApi,
  tradeCredsConfigured,
  TRADE_EMAIL,
  TRADE_PASSWORD,
} from "../helpers/api";
import {
  hasText,
  tapId,
  waitForId,
  waitForText,
  dismissKeyboard,
} from "../helpers/ui";

const tag = Date.now().toString(36);
const MESSAGE = `E2E business reply ${tag} - we can attend this week.`;

/** First element whose accessibility id starts with the given prefix. */
async function firstByIdPrefix(
  prefix: string
): Promise<WebdriverIO.Element | null> {
  const els = await (await $$(`-ios predicate string:name BEGINSWITH '${prefix}'`)).getElements();
  return els.length > 0 ? els[0] : null;
}

describe("17: trade messages (inbox + chat thread)", () => {
  if (!tradeCredsConfigured()) {
    console.log("SKIP: E2E_TRADE_EMAIL/E2E_TRADE_PASSWORD not set");
    return;
  }

  let messageSent = false;

  before(async () => {
    await loginAsTrade(TRADE_EMAIL, TRADE_PASSWORD);
  });

  after(async () => {
    if (messageSent && dbConfigured()) {
      // `body` only exists on communications/notifications; other scoped
      // tables fail silently in deleteTestData.
      await deleteTestData("body = $1", [MESSAGE]);
    }
    await closeDb();
  });

  it("renders the inbox (list or empty state)", async () => {
    await tapId("tab-messages");
    await waitForText("Messages");
    const empty = await hasText("No conversations yet");
    const hasLead = (await firstByIdPrefix("inbox-lead-")) !== null;
    expect(empty || hasLead).toBe(true);
    if (empty) {
      console.log("SKIP: inbox is empty — no lead threads to open");
    }
  });

  it("opens a lead thread", async () => {
    const lead = await firstByIdPrefix("inbox-lead-");
    if (!lead) {
      console.log("SKIP: no lead threads available");
      return;
    }
    await lead.click();
    await waitForText("Messages", 15000);
    await waitForId("chat-composer", 15000);
    await tapId("back-button", 8000).catch(() => undefined);
    await waitForText("Messages", 15000);
  });

  it("sends a message as the business and persists it outbound", async () => {
    const lead = await firstByIdPrefix("inbox-lead-");
    if (!lead) {
      console.log("SKIP: no lead threads available");
      return;
    }
    await lead.click();
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

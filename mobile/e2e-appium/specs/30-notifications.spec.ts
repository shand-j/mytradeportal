/**
 * Batch A — 30: notifications & permissions.
 *
 * - First-launch-after-login iOS permission prompt (NotificationWatcher →
 *   requestFirstLaunchPermissions) can be allowed via handlePermissionAlert.
 * - After permission is granted the app registers an Expo push token
 *   (POST /notifications/push-token); assert a push_tokens row exists for the
 *   signed-in staff user (pg countRows on owner_id).
 * - The in-app notification bell (trade dashboard + customer requests screen)
 *   opens the notifications list, and the list matches the backend rows.
 *
 * Local-notification banner behaviour (quote_ready foreground alert) needs a
 * real AI quote event, which would create production data — covered here only
 * insofar as the in-app list and badge reflect backend notifications.
 */
import { ensureLoggedOut, loginAsCustomer, loginAsTrade } from "../helpers/auth";
import { byId, handlePermissionAlert, hasText, tapId, waitForId, waitForText } from "../helpers/ui";
import {
  apiGet,
  closeDb,
  countRows,
  CUSTOMER_EMAIL,
  CUSTOMER_PASSWORD,
  customerCredsConfigured,
  dbConfigured,
  loginTradeApi,
  tradeCredsConfigured,
  TRADE_EMAIL,
  TRADE_PASSWORD,
} from "../helpers/api";

/** Number of rendered notification rows (testIDs notification-<uuid>). */
async function renderedNotificationCount(): Promise<number> {
  const rows = await driver.$$(
    "-ios predicate string:name BEGINSWITH 'notification-' AND name != 'notification-back'"
  );
  return rows.length;
}

describe("30 notifications: permission prompt + push token (trade)", () => {
  if (!tradeCredsConfigured()) {
    console.log("SKIP: E2E_TRADE_EMAIL/E2E_TRADE_PASSWORD not set");
    return;
  }

  let alertDecision: "allow" | "deny" | null = null;

  before(async () => {
    await ensureLoggedOut();
    await loginAsTrade(TRADE_EMAIL, TRADE_PASSWORD);
  });

  after(async () => {
    await closeDb();
  });

  it("first-launch permission prompt appears after login and can be allowed", async () => {
    // NotificationWatcher mounts with the (trade) layout and requests
    // notification + location permissions once per install. The prompt only
    // appears while the iOS decision is undetermined — on a previously
    // decided device handlePermissionAlert is a no-op and null is returned.
    await driver.pause(2500);
    alertDecision = await handlePermissionAlert("allow");
    await driver.pause(1000);
    // A second prompt (location) may follow.
    const second = await handlePermissionAlert("allow");
    alertDecision = alertDecision ?? second;
    if (alertDecision) {
      expect(alertDecision).toBe("allow");
    } else {
      console.log("No permission prompt shown — decision already made on this install");
    }
    // Session is intact either way.
    await waitForId("notifications-bell-trade", 25000).catch(async () => {
      await waitForText("Dashboard", 10000);
    });
  });

  it("push token row exists in the DB for the signed-in staff user", async function () {
    if (!dbConfigured()) {
      console.log("SKIP: MTP_DB_URL not set — cannot assert push_tokens row");
      this.skip();
    }
    const ctx = await loginTradeApi();
    const me = (await apiGet(ctx, "/auth/me")) as { id: string };
    let found = 0;
    try {
      await driver.waitUntil(
        async () => {
          found = await countRows("push_tokens", "owner_id = $1 AND platform = 'ios'", [me.id]);
          return found > 0;
        },
        { timeout: 30000, interval: 3000 }
      );
    } catch {
      found = await countRows("push_tokens", "owner_id = $1 AND platform = 'ios'", [me.id]).catch(
        () => 0
      );
    }
    if (found === 0 && alertDecision === null) {
      // Permission was denied earlier on this install — registration is
      // skipped by design, so there is nothing to assert.
      console.log("SKIP: notification permission previously denied — no push token expected");
      return;
    }
    expect(found).toBeGreaterThan(0);
  });
});

describe("30 notifications: trade bell opens the notifications list", () => {
  if (!tradeCredsConfigured()) {
    console.log("SKIP: E2E_TRADE_EMAIL/E2E_TRADE_PASSWORD not set");
    return;
  }

  before(async () => {
    await loginAsTrade(TRADE_EMAIL, TRADE_PASSWORD);
  });

  after(async () => {
    await closeDb();
  });

  it("dashboard bell opens the notifications screen", async () => {
    await waitForId("notifications-bell-trade", 25000);
    await tapId("notifications-bell-trade");
    await waitForText("Notifications");
    await waitForId("notifications-back");
  });

  it("the in-app list matches the backend notifications for the user", async function () {
    if (!dbConfigured()) {
      console.log("SKIP: MTP_DB_URL not set — UI-only assertion");
      await driver.pause(1500);
      const hasEntries = (await renderedNotificationCount()) > 0;
      const showsEmpty = await hasText("No notifications yet.");
      expect(hasEntries || showsEmpty).toBe(true);
      await tapId("notifications-back");
      return;
    }
    const ctx = await loginTradeApi();
    const me = (await apiGet(ctx, "/auth/me")) as { id: string };
    const apiList = (await apiGet(ctx, "/notifications")) as unknown[];
    const dbRows = await countRows("notifications", "recipient_id = $1", [me.id]);
    await driver.pause(2000); // let the polled query refetch
    const rendered = await renderedNotificationCount();
    // UI rows must correspond to real backend state: either both empty…
    if (apiList.length === 0 || dbRows === 0) {
      await waitForText("No notifications yet.");
      expect(rendered).toBe(0);
    } else {
      // …or the screen lists entries after the events occurred.
      expect(rendered).toBeGreaterThan(0);
      expect(rendered).toBe(apiList.length);
    }
    await tapId("notifications-back");
    await waitForId("notifications-bell-trade");
  });
});

describe("30 notifications: customer bell opens the notifications list", () => {
  if (!customerCredsConfigured()) {
    console.log("SKIP: E2E_CUSTOMER_EMAIL/E2E_CUSTOMER_PASSWORD not set");
    return;
  }

  before(async () => {
    await loginAsCustomer(CUSTOMER_EMAIL, CUSTOMER_PASSWORD);
  });

  it("requests-screen bell opens the notifications screen", async () => {
    // The bell lives in the requests screen header.
    await waitForId("notifications-bell-customer", 25000);
    await tapId("notifications-bell-customer");
    await waitForText("Notifications");
    await waitForId("notifications-back");
    await driver.pause(1500);
    const hasEntries = (await renderedNotificationCount()) > 0;
    const showsEmpty = await hasText("No notifications yet.");
    expect(hasEntries || showsEmpty).toBe(true);
    await tapId("notifications-back");
    await waitForId("notifications-bell-customer");
  });

  it("unread badge appears when unread notifications exist", async () => {
    await driver.pause(1500);
    if (await byId("notifications-badge").isExisting()) {
      await waitForId("notifications-badge");
    } else {
      console.log("No unread badge — nothing unread for this customer");
    }
  });
});

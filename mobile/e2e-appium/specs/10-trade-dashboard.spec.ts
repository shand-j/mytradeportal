/**
 * Trade dashboard surfaces: stats cards, header actions (three-dot settings,
 * notification bell) and bottom-tab navigation across every trade tab.
 * No data is created here — nothing to clean up.
 */
import { loginAsTrade } from "../helpers/auth";
import { byId, handlePermissionAlert, tapBack, tapId, waitForId, waitForText } from "../helpers/ui";
import { tradeCredsConfigured, TRADE_EMAIL, TRADE_PASSWORD } from "../helpers/api";

// Page-source dump on failure for device-side debugging.
async function dumpOnFailure(state?: string) {
  if (state !== "failed") return;
  const fs = await import("node:fs");
  try {
    fs.writeFileSync(`/tmp/e2e-debug-10-${Date.now()}.xml`, await driver.getPageSource());
  } catch {
    /* keep the original error */
  }
}

describe("trade dashboard", () => {
  if (!tradeCredsConfigured()) {
    console.log("SKIP: E2E_TRADE_EMAIL/E2E_TRADE_PASSWORD not set");
    return;
  }

  afterEach(async function () {
    await dumpOnFailure((this as { currentTest?: { state?: string } }).currentTest?.state);
  });

  before(async () => {
    await loginAsTrade(TRADE_EMAIL, TRADE_PASSWORD);
    // The NotificationWatcher may prompt for push permission after login.
    await driver.pause(1000);
    await handlePermissionAlert("allow");
  });

  it("renders the dashboard stats and header actions", async () => {
    await waitForText("Dashboard");
    await waitForText("Active leads");
    await waitForText("Outstanding quotes");
    await waitForId("notifications-bell-trade");
    await waitForId("dashboard-more");
  });

  it("three-dot header opens the settings screen", async () => {
    await tapId("dashboard-more");
    // NB: the dashboard three-dot IconButton carries accessibilityLabel
    // "Settings", so waiting on the word "Settings" would match the button
    // itself — wait for a settings-screen-only element instead.
    await waitForId("settings-logout");
    await tapBack();
    await waitForText("Dashboard");
  });

  it("notification bell opens the notifications screen", async () => {
    await tapId("notifications-bell-trade");
    // Same collision: the bell's accessibilityLabel is "Notifications".
    await waitForId("notifications-back");
    // The header testID sits on the container View; the tappable back
    // control inside it is `back-button`.
    await tapBack();
    await waitForText("Dashboard");
  });

  it("bottom nav reaches every trade tab", async () => {
    // Tab-bar labels persist on every trade screen, so each stop must be
    // verified by content that only exists on that screen.
    const stops: Array<[string, string]> = [
      // [tab testID, screen-unique iOS predicate]
      ["tab-quotes", `label == "+ New quote"`],
      ["tab-customers", `label == "New Customer"`],
      ["tab-calendar", `label == "+ New job"`],
      // Inbox: either the empty state or at least one conversation row.
      [
        "tab-messages",
        `name BEGINSWITH 'inbox-lead-' OR label == "No conversations yet — new quote requests will appear here."`,
      ],
      ["tab-dashboard", `label == "Active leads"`],
    ];
    for (const [tabId, predicate] of stops) {
      await tapId(tabId);
      await driver.pause(500);
      await $(`-ios predicate string:${predicate}`).waitForExist({ timeout: 15000 });
    }
  });
});

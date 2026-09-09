/**
 * Trade dashboard surfaces: stats cards, header actions (three-dot settings,
 * notification bell) and bottom-tab navigation across every trade tab.
 * No data is created here — nothing to clean up.
 */
import { loginAsTrade } from "../helpers/auth";
import { byId, handlePermissionAlert, tapBack, tapId, waitForId, waitForText } from "../helpers/ui";
import { tradeCredsConfigured, TRADE_EMAIL, TRADE_PASSWORD } from "../helpers/api";

describe("trade dashboard", () => {
  if (!tradeCredsConfigured()) {
    console.log("SKIP: E2E_TRADE_EMAIL/E2E_TRADE_PASSWORD not set");
    return;
  }

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
    await waitForText("Settings");
    await waitForId("settings-logout");
    await tapBack();
    await waitForText("Dashboard");
  });

  it("notification bell opens the notifications screen", async () => {
    await tapId("notifications-bell-trade");
    await waitForText("Notifications");
    await waitForId("notifications-back");
    await tapId("notifications-back");
    await waitForText("Dashboard");
  });

  it("bottom nav reaches every trade tab", async () => {
    const tabs: Array<[string, string]> = [
      ["tab-quotes", "Quotes"],
      ["tab-customers", "Customers"],
      ["tab-calendar", "Calendar"],
      ["tab-messages", "Messages"],
      ["tab-dashboard", "Dashboard"],
    ];
    for (const [tabId, headerText] of tabs) {
      await tapId(tabId);
      await driver.pause(500);
      await waitForText(headerText);
    }
  });
});

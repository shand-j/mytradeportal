/**
 * UI-level authentication helpers (trade + customer) and logout.
 */
import { relaunchApp } from "./app";
import { byId, dismissKeyboard, dismissPasswordPrompt, openTradeSettings, tapId, tapText, textEl, waitForId, waitForText } from "./ui";

/** Login as an electrician (tenant-agnostic, by email). */
export async function loginAsTrade(email: string, password: string) {
  // Prior specs may have left a session active — always start logged out.
  await ensureLoggedOut();
  // From the entry screen choose electrician login.
  if (await byId("entry-trade-login").isExisting()) {
    await tapId("entry-trade-login");
  } else if (await byId("entry-customer-login").isExisting()) {
    await tapId("entry-customer-login");
  }
  await waitForText("Electrician login");
  await fillLoginForm(email, password);
  await waitForId("settings-logout", 25000).catch(async () => {
    // Landing on dashboard; the settings button may be behind the three-dot
    // menu on some screens, so just wait for a known dashboard surface.
    await waitForText("Dashboard", 10000).catch(() => undefined);
  });
}

/** Login as an existing customer by email. */
export async function loginAsCustomer(email: string, password: string) {
  await ensureLoggedOut();
  if (await byId("entry-customer-login").isExisting()) {
    await tapId("entry-customer-login");
  }
  await waitForText("Customer login");
  await fillLoginForm(email, password);
}

async function fillLoginForm(email: string, password: string) {
  const emailField = await waitForId("login-email");
  await emailField.click();
  await emailField.setValue(email);
  const passwordField = await waitForId("login-password");
  await passwordField.click();
  await passwordField.setValue(password);
  await dismissKeyboard();
  await tapId("login-submit");
  // iOS Keychain may offer to save the password — decline so it never
  // swallows taps on the next screen.
  await dismissPasswordPrompt();
}

/**
 * Ensure the app is logged out. If a session is active, opens settings and
 * logs out; otherwise no-ops. Call before tests that need the entry screen.
 */
export async function ensureLoggedOut() {
  await relaunchApp();
  // Session screens share a bottom tab bar with a settings route; if we are
  // anywhere in a group the logout button lives on the settings screen.
  // Cheap probe: try opening trade settings via deep link is unavailable on
  // the TestFlight build, so probe for entry markers first.
  if ((await byId("entry-trade-login").isExisting()) || (await byId("entry-customer-login").isExisting())) {
    return;
  }
  // We are inside a session. Screens reached mid-flow (e.g. manual lead
  // entry) have neither header-settings nor any "Settings" label — go via
  // the dashboard tab, whose three-dot button carries the "Settings" label.
  // Stack screens (job create, quote edit) have no tab bar: back out until
  // it appears.
  for (let i = 0; i < 6 && !(await byId("tab-dashboard").isExisting()); i++) {
    const back = byId("back-button");
    if (!(await back.isExisting())) break;
    await back.click();
    await driver.pause(500);
  }
  const dashTab = byId("tab-dashboard");
  if (await dashTab.isExisting()) {
    await dashTab.click();
    await driver.pause(600);
  }
  // Customer session: no dashboard tab — the header carries a "Profile"
  // action and the logout button lives on that screen.
  if (!(await byId("tab-dashboard").isExisting()) && (await textEl("Profile").isExisting())) {
    await tapText("Profile", 8000);
    await tapText("Log out", 15000);
    await driver.pause(1000);
    return;
  }
  await openTradeSettings();
  const logout = await waitForId("settings-logout", 20000).catch(async (err) => {
    const fs = await import("node:fs");
    try {
      fs.writeFileSync(`/tmp/e2e-debug-logout-${Date.now()}.xml`, await driver.getPageSource());
    } catch {
      /* keep the original error */
    }
    throw err;
  });
  await logout.click();
  await driver.pause(1000);
}

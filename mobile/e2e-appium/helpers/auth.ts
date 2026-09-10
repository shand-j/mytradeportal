/**
 * UI-level authentication helpers (trade + customer) and logout.
 */
import { relaunchApp } from "./app";
import { byId, dismissKeyboard, dismissPasswordPrompt, tapId, waitForId, waitForText, tapText } from "./ui";

/** Login as an electrician (tenant-agnostic, by email). */
export async function loginAsTrade(email: string, password: string) {
  await relaunchApp();
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
  await relaunchApp();
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
  // We are inside a session — the three-dot header opens Settings, where the
  // logout button lives.
  const headerSettings = byId("header-settings");
  if (await headerSettings.isExisting()) {
    await headerSettings.click();
  } else {
    await tapText("Settings", 8000).catch(() => undefined);
  }
  const logout = await waitForId("settings-logout", 12000);
  await logout.click();
  await driver.pause(1000);
}

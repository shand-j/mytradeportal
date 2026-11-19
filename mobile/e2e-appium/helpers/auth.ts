/**
 * UI-level authentication helpers (trade + customer) and logout.
 */
import { relaunchApp } from "./app";
import { byId, dismissKeyboard, dismissPasswordPrompt, openTradeSettings, tapId, tapText, textEl, textElContains, waitForId, waitForText } from "./ui";

/**
 * Drill through the entry screen's role select if it is showing. The role
 * cards gate the login/register buttons, so any spec touching entry-* IDs
 * calls this first. No-op when a white-label business card or a role screen
 * is already displayed.
 */
export async function pickRole(role: "electrician" | "customer") {
  const select = byId("role-select");
  // Right after a relaunch the splash/entry tree takes seconds to mount; an
  // instant isExisting() probe misreads that window as "not on role select"
  // and skips the tap, stranding the caller on the role screen. Wait briefly
  // instead; no-op only when role-select genuinely never appears (white-label
  // business card, or a role screen already displayed).
  const visible = await select
    .waitForExist({ timeout: 15000 })
    .then(() => true)
    .catch(() => false);
  if (visible) {
    await tapId(`role-${role}`);
  }
}

/** Login as an electrician (tenant-agnostic, by email). */
export async function loginAsTrade(email: string, password: string) {
  // Prior specs may have left a session active — always start logged out.
  await ensureLoggedOut();
  // From the entry screen choose electrician login.
  await pickRole("electrician");
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
  await pickRole("customer");
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
  // Let the auth store rehydrate before probing: right after launch the app
  // can render the entry screen briefly even when a session exists, and a
  // probe in that window misreads "logged out".
  await driver.pause(2500);
  // Session screens share a bottom tab bar with a settings route; if we are
  // anywhere in a group the logout button lives on the settings screen.
  // Cheap probe: try opening trade settings via deep link is unavailable on
  // the TestFlight build, so probe for entry markers first.
  // The RN tree can take ~10s to mount after a cold launch, and before it
  // does NO markers exist — an instant probe misreads that window as
  // "inside a session". Wait for the markers before concluding anything.
  const entryMarker = await Promise.race([
    byId("entry-trade-login")
      .waitForExist({ timeout: 12000 })
      .then(() => true)
      .catch(() => false),
    byId("role-select")
      .waitForExist({ timeout: 12000 })
      .then(() => true)
      .catch(() => false),
  ]);
  if (entryMarker) {
    return;
  }
  // We are inside a session. A cold launch with a persisted session can
  // spend 15s+ on splash + auth rehydrate + first data fetch before the tab
  // bar mounts, so WAIT for the dashboard tab rather than instant-probing.
  // Stack screens (job create, quote edit) hide the tab bar: back out until
  // it appears.
  const dashTab = byId("tab-dashboard");
  let tradeShell = await dashTab
    .waitForExist({ timeout: 20000 })
    .then(() => true)
    .catch(() => false);
  for (let i = 0; i < 6 && !tradeShell; i++) {
    const back = byId("back-button");
    if (!(await back.isExisting())) break;
    await back.click();
    await driver.pause(500);
    tradeShell = await dashTab.isExisting();
  }
  if (tradeShell) {
    await dashTab.click();
    await driver.pause(600);
  }
  // Customer session: no dashboard tab — the profile screen carries the
  // logout button. New builds reach it via the bottom `tab-profile` tab;
  // older builds via a header "Profile" action. The customer tab bar can be
  // just as slow to mount as the trade one, so wait for it too.
  if (!tradeShell) {
    const profileTab = byId("tab-profile");
    const profileVisible = await profileTab
      .waitForExist({ timeout: 15000 })
      .then(() => true)
      .catch(() => false);
    if (profileVisible) {
      await profileTab.click();
      await driver.pause(600);
    } else if (await textEl("Profile").isExisting()) {
      await tapText("Profile", 8000);
    }
    // The logout Button collapses into a composite-label element — match
    // by containment, not exact label.
    await textElContains("Log out").waitForExist({ timeout: 15000 });
    await textElContains("Log out").click();
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

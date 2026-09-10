/**
 * Batch A — 01: pre-auth entry + auth surfaces.
 *
 * Covers the logged-out entry screen (default + white-label business card),
 * login form validation, invalid-credentials errors (trade + customer), the
 * forgot-password confirmation, and a surface check of the reset-password
 * deep-link screen (app/reset-password.tsx). No real accounts are created or
 * mutated: invalid logins use throwaway addresses and the reset flow is only
 * exercised with an invalid token.
 */
import { relaunchApp } from "../helpers/app";
import { ensureLoggedOut, pickRole } from "../helpers/auth";
import {
  byId,
  dismissKeyboard,
  hasText,
  tapBack,
  tapId,
  textElContains,
  waitForId,
  waitForText,
} from "../helpers/ui";
import { dbConfigured, findTenantBySlug, TENANT_SLUG } from "../helpers/api";
import { BUNDLE_ID } from "../helpers/env";

const tag = Date.now().toString(36);

/** Fill the CodeInput (six single-digit boxes, digits only).
 *
 * Empty RN TextInputs without placeholders are absent from the XCUITest
 * tree, so we first tap the code card to focus the first box, then type
 * digits — via setValue when the box is queryable, else via the keyboard.
 */
async function enterBusinessCode(code: string) {
  // The code card lives behind the customer role option.
  await pickRole("customer");
  const digits = code.replace(/\D/g, "").slice(0, 6).padEnd(6, "0");
  // Focus the first code box: tap below the code-card label (the boxes sit
  // between the label and the Find button). Empty RN TextInputs only appear
  // in the XCUITest tree once focused.
  const label = await waitForText("Enter your electrician's code or business slug");
  const loc = await label.getLocation();
  const size = await driver.getWindowSize();
  const x = Math.min(Math.round(loc.x + 20), Math.round(size.width / 2));
  const y = Math.round(loc.y + 50);
  await driver.performActions([
    {
      type: "pointer",
      id: "tap",
      parameters: { pointerType: "touch" },
      actions: [
        { type: "pointerMove", duration: 0, x, y },
        { type: "pointerDown", button: 0 },
        { type: "pointerUp", button: 0 },
      ],
    },
  ]);
  await driver.releaseActions();
  await driver.pause(800);
  for (let i = 0; i < 6; i++) {
    const box = byId(`business-code-${i}`);
    if (await box.isExisting()) {
      await box.setValue(digits[i]);
    } else {
      const key = await driver.$(
        `-ios predicate string:(type == 'XCUIElementTypeKey' OR type == 'XCUIElementTypeButton') AND label == '${digits[i]}'`
      );
      await key.waitForExist({ timeout: 5000 });
      await key.click();
    }
    await driver.pause(200);
  }
  await dismissKeyboard();
}

describe("01 entry: pre-auth surfaces", () => {
  before(async () => {
    await ensureLoggedOut();
  });

  it("renders the splash then the role select with both role surfaces", async () => {
    await relaunchApp();
    // Cold open: animated splash (module-flagged, once per session).
    await waitForId("splash", 15000);
    await waitForId("role-select", 15000);
    await waitForText("Get started");
    await waitForText("I'm an Electrician");
    await waitForText("I'm a Customer");

    // Customer side: code lookup + customer login.
    await tapId("role-customer");
    await waitForText("Enter your electrician's code or business slug");
    await waitForId("entry-find-business");
    await waitForId("entry-customer-login");
    await tapId("back-button");
    await waitForId("role-select");

    // Electrician side: login + registration.
    await tapId("role-electrician");
    await waitForId("entry-trade-login");
    await waitForId("entry-register-trade");
    await tapId("back-button");
    await waitForId("role-select");
  });

  it("tapping Find my electrician with no code stays on the customer view", async () => {
    // The button is disabled until a digit is entered; a tap must not
    // navigate anywhere.
    await pickRole("customer");
    await tapId("entry-find-business");
    await driver.pause(600);
    expect(await hasText("My Trade Portal")).toBe(true);
    expect(await byId("entry-request-quote").isExisting()).toBe(false);
  });

  it("rejects an unknown business code with an inline error", async () => {
    await enterBusinessCode("000000");
    await tapId("entry-find-business");
    await waitForText("We couldn't find a business with that code. Please check and try again.", 25000);
  });

  it("finds a real business by code and shows Request a quote on the card", async function () {
    if (!dbConfigured() || !TENANT_SLUG) {
      console.log("SKIP: MTP_DB_URL / E2E_TENANT_SLUG not set — cannot resolve a real business code");
      this.skip();
    }
    const tenant = await findTenantBySlug(TENANT_SLUG);
    const code = String(tenant?.code ?? "");
    if (!code) {
      console.log(`SKIP: tenant ${TENANT_SLUG} has no numeric code`);
      this.skip();
    }
    await relaunchApp();
    await enterBusinessCode(code);
    await tapId("entry-find-business");
    // White-label business card.
    await waitForText("Your electrician", 25000);
    const name = String(tenant?.name ?? "");
    if (name) await waitForText(name);
    // Both business-card actions render.
    await waitForId("entry-request-quote");
    await waitForId("entry-customer-login");
  });

  it("Request a quote opens the customer quote request flow", async function () {
    if (!dbConfigured() || !TENANT_SLUG) {
      console.log("SKIP: needs a loaded business card from the previous test");
      this.skip();
    }
    // Re-enter the code if the business card is not showing (each it must be
    // able to run after a relaunch).
    if (!(await byId("entry-request-quote").isExisting())) {
      const tenant = await findTenantBySlug(TENANT_SLUG);
      await enterBusinessCode(String(tenant?.code ?? "000000"));
      await tapId("entry-find-business");
      await waitForText("Your electrician", 25000);
    }
    await tapId("entry-request-quote");
    await waitForId("customer-quote-flow");
    await (await textElContains("Step 1 of")).waitForExist({ timeout: 15000 });
    // Back out of the flow → business card, then back again → customer view.
    await tapBack();
    await waitForId("entry-request-quote");
    await tapBack();
    await waitForId("entry-customer-login");
  });
});

describe("01 entry: login form validation", () => {
  before(async () => {
    await ensureLoggedOut();
  });

  it("trade login: submitting with empty fields stays on the login form", async () => {
    await pickRole("electrician");
    await tapId("entry-trade-login");
    await waitForText("Electrician login");
    // Button is disabled while email/password are empty — a tap is a no-op.
    await tapId("login-submit");
    await driver.pause(600);
    await waitForText("Electrician login");
    expect(await byId("login-error").isExisting()).toBe(false);
  });

  it("forgot password without an email shows an inline validation error", async () => {
    await tapId("login-forgot-password");
    await waitForText("Enter your email above so we know where to send the reset link.");
  });
});

describe("01 entry: invalid credentials", () => {
  before(async () => {
    await ensureLoggedOut();
  });

  it("trade login with bad credentials shows Invalid email or password.", async () => {
    await pickRole("electrician");
    await tapId("entry-trade-login");
    await waitForText("Electrician login");
    const email = await waitForId("login-email");
    await email.click();
    await email.setValue(`e2e-bad-${tag}@example.test`);
    const password = await waitForId("login-password");
    await password.click();
    await password.setValue("definitely-wrong-pass");
    await dismissKeyboard();
    await tapId("login-submit");
    await waitForId("login-error", 25000);
    await waitForText("Invalid email or password.");
    await tapBack();
  });

  it("customer login with bad credentials shows Invalid email or password.", async () => {
    await relaunchApp();
    await pickRole("customer");
    await tapId("entry-customer-login");
    await waitForText("Customer login");
    const email = await waitForId("login-email");
    await email.click();
    await email.setValue(`e2e-bad-${tag}@example.test`);
    const password = await waitForId("login-password");
    await password.click();
    await password.setValue("definitely-wrong-pass");
    await dismissKeyboard();
    await tapId("login-submit");
    await waitForId("login-error", 25000);
    await waitForText("Invalid email or password.");
    await tapBack();
  });
});

describe("01 entry: forgot password", () => {
  before(async () => {
    await ensureLoggedOut();
  });

  it("requesting a reset link confirms 'we've emailed a reset link'", async () => {
    await pickRole("electrician");
    await tapId("entry-trade-login");
    await waitForText("Electrician login");
    // A throwaway address: the API response is generic, so the confirmation
    // shows regardless and no real inbox receives mail.
    const email = await waitForId("login-email");
    await email.click();
    await email.setValue(`e2e-reset-${tag}@example.test`);
    await dismissKeyboard();
    await tapId("login-forgot-password");
    await waitForId("login-reset-sent", 25000);
    const confirmation = await textElContains("we've emailed a reset link");
    await confirmation.waitForExist({ timeout: 15000 });
  });
});

describe("01 entry: reset password deep link", () => {
  before(async () => {
    await ensureLoggedOut();
  });

  it("mtp://reset-password surfaces the set-new-password screen", async () => {
    // Surface check only (app/reset-password.tsx): open the route with a
    // bogus token — the form renders, client-side validation fires, and the
    // API rejects the token without mutating anything.
    let opened = false;
    try {
      await driver.execute("mobile: deepLink", {
        url: `mtp://reset-password?token=e2e-invalid-${tag}`,
        bundleId: BUNDLE_ID,
      });
      opened = true;
    } catch (err) {
      console.log(`mobile: deepLink unsupported (${String(err)}), trying driver.url fallback`);
      try {
        await driver.url(`mtp://reset-password?token=e2e-invalid-${tag}`);
        opened = true;
      } catch (err2) {
        console.log(`SKIP: cannot open deep links on this device (${String(err2)})`);
      }
    }
    if (!opened) return;

    await waitForText("Set a new password", 20000);
    const password = await waitForId("reset-new-password");
    await password.click();
    await password.setValue("short");
    await waitForId("reset-hint-too-short");
    await waitForText("Password must be at least 12 characters.");
    await password.setValue("E2E Password123");
    const confirm = await waitForId("reset-confirm-password");
    await confirm.click();
    await confirm.setValue("Different Pass123");
    await dismissKeyboard();
    await waitForId("reset-hint-mismatch");
    await waitForText("The passwords don't match.");
    await confirm.setValue("E2E Password123");
    await dismissKeyboard();
    await tapId("reset-submit");
    // The bogus token is rejected by the server — proves the form submits.
    await waitForId("reset-error", 25000);
    await waitForText("This reset link is invalid or has expired. Request a new one from the login screen.");
  });

  it("mtp://reset-password without a token shows the missing-token surface", async () => {
    let opened = false;
    try {
      await driver.execute("mobile: deepLink", { url: "mtp://reset-password", bundleId: BUNDLE_ID });
      opened = true;
    } catch {
      try {
        await driver.url("mtp://reset-password");
        opened = true;
      } catch (err) {
        console.log(`SKIP: cannot open deep links on this device (${String(err)})`);
      }
    }
    if (!opened) return;
    await waitForText("Missing reset token", 20000);
    await waitForText("Open the reset link from the email we sent you.");
    await waitForId("reset-back-to-login");
    await tapId("reset-back-to-login");
    await waitForText("My Trade Portal", 20000);
  });
});

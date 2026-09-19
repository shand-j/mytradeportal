/**
 * Batch A — 02: tenant onboarding wizard (app/onboarding → OnboardingStepperScreen).
 *
 * Walks every step of the wizard with a unique-tagged throwaway identity,
 * asserting each step's validation blocks Continue until the step is complete.
 * Stops at the Review step: tapping "Choose your plan" there would POST
 * /tenants and provision a REAL tenant (finishRegistration runs before the
 * plan/Paddle step), which we must not do against production. The plan step
 * itself therefore cannot be rendered without creating a tenant — its entry
 * point (onboarding-choose-plan) is asserted instead.
 *
 * No backend rows are created, so no cleanup is required; the wizard state is
 * in-memory only and is discarded by relaunchApp() in the after hook.
 */
import { relaunchApp } from "../helpers/app";
import { ensureLoggedOut, pickRole } from "../helpers/auth";
import { tapBack, tapId, tapText, textEl, textElContains, waitForId, waitForText, dismissKeyboard, dismissPasswordPrompt } from "../helpers/ui";

const tag = Date.now().toString(36);
const FULL_NAME = `E2E Tester ${tag}`;
const EMAIL = `e2e-onboarding-${tag}@example.test`;
const TRADING_NAME = `E2E Electrical ${tag}`;

// Onboarding FormField inputs carry no testIDs, so we target the native
// TextField/TextView by its placeholder value (unique per field on this
// screen) — verified against the step sources.
function esc(s: string): string {
  return s.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
}

async function fieldByPlaceholder(placeholder: string): Promise<WebdriverIO.Element> {
  const escaped = esc(placeholder);
  const tf = $(
    `-ios class chain:**/XCUIElementTypeTextField[\`placeholderValue == "${escaped}"\`]`
  );
  if (await tf.isExisting()) return (await tf) as unknown as WebdriverIO.Element;
  const secure = $(
    `-ios class chain:**/XCUIElementTypeSecureTextField[\`placeholderValue == "${escaped}"\`]`
  );
  if (await secure.isExisting()) return (await secure) as unknown as WebdriverIO.Element;
  const tv = $(
    `-ios class chain:**/XCUIElementTypeTextView[\`placeholderValue == "${escaped}"\`]`
  );
  if (await tv.isExisting()) return (await tv) as unknown as WebdriverIO.Element;
  // RN multiline TextInputs render the placeholder as a child StaticText
  // rather than exposing placeholderValue on the TextView — tap the
  // placeholder text to focus the field, then use the active TextView.
  const phText = await textEl(placeholder);
  if (await phText.isExisting()) {
    await phText.click();
    await driver.pause(400);
    const anyTv = $(`-ios predicate string:type == 'XCUIElementTypeTextView'`);
    await anyTv.waitForExist({ timeout: 5000 });
    return (await anyTv) as unknown as WebdriverIO.Element;
  }
  await tv.waitForExist({ timeout: 15000 });
  return (await tv) as unknown as WebdriverIO.Element;
}

async function setFieldByPlaceholder(placeholder: string, value: string) {
  const el = await fieldByPlaceholder(placeholder);
  await el.click();
  await el.setValue(value);
  await driver.pause(250);
}

async function readFieldByPlaceholder(placeholder: string): Promise<string> {
  const el = await fieldByPlaceholder(placeholder);
  const value = await el.getAttribute("value");
  return String(value ?? "");
}


/** Wait for text matched by substring (device copy carries bullet prefixes). */
async function waitForTextContains(label: string, timeoutMs = 15000) {
  const el = textElContains(label);
  await el.waitForExist({ timeout: timeoutMs });
  return el;
}

/** Assert we are still on the given step (validation blocked Continue). */
async function expectStep(label: string) {
  await waitForText(`Step ${label}`);
}

describe("02 onboarding: wizard walk-through (stops before tenant creation)", () => {
  before(async () => {
    await ensureLoggedOut();
    await pickRole("electrician");
    await tapId("entry-register-trade");
    await waitForText("Run your electrical business from your phone.", 25000);
  });

  after(async () => {
    // Wizard state is in-memory; a fresh launch returns to the entry screen.
    await ensureLoggedOut();
  });

  it("step 1 Welcome renders the value props and launch preview", async () => {
    await expectStep("1 of 12: Welcome");
    await waitForTextContains("Get leads from QR codes");
    await waitForTextContains("AI drafts quotes");
    await waitForTextContains("Certificates, invoices, and accounts");
    await waitForText("6-step launch preview");
    for (const label of ["Account", "Business", "Address", "Tax", "Compliance", "Services"]) {
      await waitForText(label);
    }
    await waitForText("I already have an account");
  });

  it("step 2 Account: Continue is blocked until the form is valid", async () => {
    await tapText("Create my account");
    await expectStep("2 of 12: Account");
    await waitForText("This is how you’ll log in to manage your business.");
    // Incomplete form — tapping Continue must not advance.
    await setFieldByPlaceholder("Full name", FULL_NAME);
    await dismissKeyboard();
    await tapText("Continue");
    await driver.pause(500);
    await expectStep("2 of 12: Account");
  });

  it("step 2 Account: role chips, terms checkbox and completed form advance", async () => {
    await setFieldByPlaceholder("you@business.com", EMAIL);
    await setFieldByPlaceholder("07700 123 456", "07700123456");
    await setFieldByPlaceholder("At least 8 characters", "E2E Passw0rd!");
    await dismissKeyboard();
    // Password strength meter reacts (Weak → Strong as length grows).
    await waitForText("Strong");
    // Non-owner roles surface the owner-only hint.
    await tapText("Engineer");
    await waitForTextContains("Only owners can complete billing and team settings.");
    await tapText("Owner");
    // Terms checkbox (a Pressable, not a Button — tap its label text).
    await tapText("I accept the Terms of Service and Privacy Notice.");
    await tapText("Continue");
    // Successful password form → iOS Keychain "Save Password?" sheet.
    await dismissPasswordPrompt();
    await expectStep("3 of 12: Identity");
  });

  it("step 3 Identity: trading name required, structure chips toggle fields", async () => {
    // iOS Keychain may offer to save the step-2 password — decline it, or it
    // swallows every tap on this step.
    await dismissPasswordPrompt();
    await waitForTextContains("Customers see this on quotes");
    await tapText("Continue");
    await driver.pause(500);
    await expectStep("3 of 12: Identity"); // blocked: no trading name
    await setFieldByPlaceholder("e.g. Smith Electrical Ltd", TRADING_NAME);
    await dismissKeyboard();
    // Sole trader shows the MTD hint…
    await tapText("Sole trader");
    await waitForText("MTD hint");
    // …and Limited company swaps in the Companies House field.
    await tapText("Limited company");
    await waitForText("Companies House number");
    await setFieldByPlaceholder("12345678", "12345678");
    await setFieldByPlaceholder("YYYY", "2020");
    await setFieldByPlaceholder("e.g. 6", "6");
    await setFieldByPlaceholder("e.g. 45", "45");
    await dismissKeyboard();
    await tapText("Continue");
    await expectStep("4 of 12: Address");
  });

  it("step 4 Address: postcode and address are required to continue", async () => {
    await tapText("Continue");
    await driver.pause(500);
    await expectStep("4 of 12: Address"); // blocked
    await setFieldByPlaceholder("e.g. SK8 3NJ", "SK8 3NJ");
    await setFieldByPlaceholder("Full trading address", "1 Test Way, Cheadle, Manchester");
    // Defocus the multiline field by tapping its label (Return would insert
    // a newline here rather than dismiss the keyboard).
    await tapText("Trading address");
    // Service-area mode chips + nations chips render.
    await waitForText("Radius from base");
    await waitForText("Postcode list");
    await waitForText("Nations served");
    await tapText("Continue");
    await expectStep("5 of 12: Tax");
  });

  it("step 5 Tax: VAT toggle reveals VAT fields, No keeps it simple", async () => {
    await waitForText("Are you VAT registered?");
    await tapText("Yes");
    await waitForText("VAT number");
    await setFieldByPlaceholder("GB123456789", "GB123456789");
    await waitForText("Verify VAT number");
    await waitForText("Online VAT verification is not yet implemented.");
    await waitForText("20% (read-only)");
    await dismissKeyboard();
    await tapText("No");
    await tapText("Continue");
    await expectStep("6 of 12: Compliance");
  });

  it("step 6 Compliance: scheme, membership, qualifications and insurance", async () => {
    await waitForTextContains("build trust with customers");
    await tapText("NICEIC");
    await setFieldByPlaceholder("e.g. NE12345", "NE12345");
    await dismissKeyboard();
    await tapText("18th Edition held");
    await waitForText("Public liability insurance");
    await setFieldByPlaceholder("e.g. AXA", "AXA");
    await setFieldByPlaceholder("e.g. PL-123456", "PL-123456");
    await dismissKeyboard();
    await tapText("£2m");
    await waitForText("DD-MM-YYYY");
    await tapText("Continue");
    await expectStep("7 of 12: Services");
  });

  it("step 7 Services: Continue blocked until at least one service is chosen", async () => {
    await waitForTextContains("Choose the jobs you want to quote for");
    await tapText("Continue");
    await driver.pause(500);
    await expectStep("7 of 12: Services"); // blocked: nothing selected
    await tapText("EV charger");
    await tapText("EICR");
    await tapText("Continue");
    await expectStep("8 of 12: Branding");
  });

  it("step 8 Branding: hex validation and preset swatches", async () => {
    await waitForTextContains("Brand colour");
    const hexField = await fieldByPlaceholder("#FFC107");
    await hexField.setValue("not-a-colour");
    await waitForText("Enter a valid hex colour, e.g. #FFC107");
    await hexField.clearValue();
    await hexField.setValue("#FFC107");
    await dismissKeyboard();
    // Preset swatches are the only testID'd inputs on this step.
    await tapId("brand-colour-059669");
    await waitForId("brand-colour-preview");
    await tapId("branding-continue");
    await expectStep("9 of 12: Review");
  });

  it("step 9 Review: summary reflects entered data; plan entry point renders", async () => {
    await waitForText("Check the details below, then choose your plan to go live.");
    // Launch-gate checklist renders completed + pending items.
    await waitForText("Account created");
    await waitForText("Business identity");
    await waitForText("Team & capacity");
    await waitForText("Data import");
    // Compliance summary shows the step-6 data.
    //
    // KNOWN APP DEFECT (fixed in app code, pending a new device build): the
    // stepper passed each step only its own state slice, so this review step
    // rendered "No Competent Person Scheme selected" / "No public liability
    // insurance added yet." even after a fully completed step 6, and omitted
    // the services summary. OnboardingStepperScreen now passes the root state
    // to the review step. These assertions fail against builds predating
    // that fix.
    await waitForText("CPS: NICEIC (NE12345)");
    await waitForText("18th Edition held");
    await waitForText("Public liability: AXA - PL-123456");
    await waitForText("Cover: £2m");
    // Services summary shows the step-7 picks.
    await waitForText("ev charger · eicr");
    // The plan entry point renders — but tapping it would POST /tenants and
    // provision a REAL tenant (finishRegistration runs at this transition,
    // before any Paddle checkout), so we assert and stop here.
    await waitForId("onboarding-choose-plan");
  });

  it("back navigation preserves in-app data entered on earlier steps", async () => {
    // Review → Branding → Services → Compliance → Tax → Address → Identity.
    for (let i = 0; i < 6; i++) {
      await tapBack();
      await driver.pause(400);
    }
    await expectStep("3 of 12: Identity");
    expect(await readFieldByPlaceholder("e.g. Smith Electrical Ltd")).toBe(TRADING_NAME);
    // One more back → Account: email and full name must still be there.
    await tapBack();
    await expectStep("2 of 12: Account");
    expect(await readFieldByPlaceholder("you@business.com")).toBe(EMAIL);
    expect(await readFieldByPlaceholder("Full name")).toBe(FULL_NAME);
  });

  it("leaving the wizard from step 1 returns to the entry screen", async () => {
    // Walk back to the welcome step, then use the header back (logout path).
    await tapBack(); // → Welcome
    await expectStep("1 of 12: Welcome");
    await tapBack(); // goBack on step 1 → logout → entry
    await waitForText("My Trade Portal", 20000);
    await relaunchApp();
  });
});

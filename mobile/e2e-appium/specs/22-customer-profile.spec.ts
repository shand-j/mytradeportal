/**
 * 22 — Customer profile: persisted details from the backend render in the
 * form, editing gives UI feedback, the screen scrolls (keyboard avoidance)
 * and the back button returns to requests.
 *
 * Known gap (app TODO): ProfileScreen.save() only flips a local "saved"
 * toast — there is no backend customer-profile PATCH endpoint, so edits do
 * NOT persist. This spec therefore asserts persistence in the read direction
 * (DB → UI pre-fill) and verifies the save feedback; it also documents that
 * the backend record is unchanged after "Save changes".
 *
 * Selector note: the profile FormFields have no testIDs — fields are located
 * as the screen's XCUIElementTypeTextField elements in render order
 * (name, email, phone); the address box is the XCUIElementTypeTextView.
 */
import { loginAsCustomer } from "../helpers/auth";
import {
  closeDb,
  customerCredsConfigured,
  CUSTOMER_EMAIL,
  CUSTOMER_PASSWORD,
} from "../helpers/api";
import { API_BASE } from "../helpers/env";
import {
  hasText,
  scrollToTextAndTap,
  tapId,
  waitForId,
  waitForText,
} from "../helpers/ui";

const tag = Date.now().toString(36);

type CustomerMe = {
  full_name?: string;
  email?: string;
  phone?: string | null;
  address?: string | null;
};

/** Local login against the customer portal (helpers only cover staff). */
async function loginCustomerApi(): Promise<{ token: string; customer: CustomerMe }> {
  const res = await fetch(`${API_BASE}/customer/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: CUSTOMER_EMAIL, password: CUSTOMER_PASSWORD }),
  });
  if (!res.ok) throw new Error(`customer API login failed: ${res.status}`);
  const body = (await res.json()) as { accessToken: string; customer: CustomerMe };
  return { token: body.accessToken, customer: body.customer };
}

async function fieldValue(el: { getText: () => Promise<string> }): Promise<string> {
  const raw: string | undefined = await el.getText().catch(() => "");
  return raw ?? "";
}

describe("22: customer profile", () => {
  if (!customerCredsConfigured()) {
    console.log("SKIP: E2E_CUSTOMER_EMAIL/E2E_CUSTOMER_PASSWORD not set");
    return;
  }

  before(async () => {
    await loginAsCustomer(CUSTOMER_EMAIL, CUSTOMER_PASSWORD);
  });

  after(async () => {
    await closeDb();
  });

  it("shows persisted profile details from the backend", async () => {
    const { customer } = await loginCustomerApi();
    await tapId("tab-profile", 25000);
    await waitForText("Profile", 15000);
    await waitForText("Personal details", 15000);

    // Render order: Full name, Email, Phone.
    const fields = await (await $$("-ios class chain:**/XCUIElementTypeTextField")).getElements();
    expect(fields.length).toBeGreaterThanOrEqual(3);
    expect(await fieldValue(fields[0])).toBe(customer.full_name ?? "");
    expect(await fieldValue(fields[1])).toBe(customer.email ?? "");
    const phone = await fieldValue(fields[2]);
    if (customer.phone) expect(phone).toBe(customer.phone);

    const addressBox = await $("-ios class chain:**/XCUIElementTypeTextView");
    await addressBox.waitForExist({ timeout: 15000 });
    const address = await fieldValue(addressBox);
    if (customer.address) expect(address).toBe(customer.address);
  });

  it("edits details, scrolls with the keyboard, and shows saved feedback", async () => {
    await tapId("tab-profile", 25000);
    await waitForText("Personal details", 15000);
    const fields = await $$("-ios class chain:**/XCUIElementTypeTextField");
    const phoneField = fields[2];
    await phoneField.click();
    await phoneField.setValue(`07123 456${tag.slice(-3)}`);
    await driver.hideKeyboard().catch(() => undefined);

    // Keyboard-avoiding scroll: the Save button stays reachable and tappable.
    await scrollToTextAndTap("Save changes", { timeoutMs: 25000 });
    await waitForText("Changes saved", 15000);

    // Known app gap: edits are local-only (ProfileScreen.save TODO). The
    // backend record must be untouched — assert and document.
    const { customer } = await loginCustomerApi();
    expect(customer.phone ?? "").not.toContain(tag.slice(-3));
  });

  it("back button returns to the requests screen", async () => {
    await tapId("tab-profile", 25000);
    await waitForText("Profile", 15000);
    await tapId("back-button", 8000);
    await waitForId("request-new-quote", 25000);
    expect(await hasText("Track your quote requests")).toBe(true);
  });
});

/**
 * 18 — Trade settings: identity + plan card, billing screen shows plans,
 * business profile fields persist from the API (contact phone/address),
 * branding colour picker persists via PATCH /tenants/me and survives a
 * relaunch, then the original colour is restored. Logout returns to entry.
 *
 * Selector note: BrandingSettingsScreen's FormFields carry no testIDs, so the
 * four text fields (name, phone, address, hex) are located as the screen's
 * XCUIElementTypeTextField elements in render order; the swatches are tapped
 * by their accessibility label ("Brand colour #RRGGBB").
 */
import { relaunchApp } from "../helpers/app";
import { loginAsTrade } from "../helpers/auth";
import {
  apiGet,
  apiPatch,
  closeDb,
  loginTradeApi,
  tradeCredsConfigured,
  TRADE_EMAIL,
  TRADE_PASSWORD,
  type ApiTenantContext,
} from "../helpers/api";
import {
  byId,
  openTradeSettings,
  tapId,
  tapText,
  textElContains,
  waitForId,
  waitForText,
} from "../helpers/ui";

const NEW_COLOUR = "#059669"; // emerald swatch in BRAND_COLOURS

type TenantMe = {
  name?: string;
  phone?: string | null;
  address?: string | null;
  primaryColor?: string | null;
};

async function fieldValue(el: { getText: () => Promise<string> }): Promise<string> {
  const raw: string | undefined = await el.getText().catch(() => "");
  return raw ?? "";
}

describe("18: trade settings, branding, billing, logout", () => {
  if (!tradeCredsConfigured()) {
    console.log("SKIP: E2E_TRADE_EMAIL/E2E_TRADE_PASSWORD not set");
    return;
  }

  let ctx: ApiTenantContext;
  let original: TenantMe = {};
  let colourChanged = false;

  before(async () => {
    await loginAsTrade(TRADE_EMAIL, TRADE_PASSWORD);
    ctx = await loginTradeApi();
    original = (await apiGet(ctx, "/tenants/me")) as TenantMe;
  });

  after(async () => {
    if (colourChanged && original.primaryColor) {
      // TenantUpdate declares camelCase aliases (primaryColor); snake_case
      // input is silently ignored by the schema.
      await apiPatch(ctx, "/tenants/me", { primaryColor: original.primaryColor });
    }
    await closeDb();
  });

  it("settings shows signed-in identity and subscription plan", async () => {
    await openTradeSettings();
    await waitForText("Settings");
    await waitForId("settings-logout");
    await waitForText(TRADE_EMAIL, 15000);
    // Either an active plan card ("… plan") or the choose-plan CTA.
    const hasPlan = await byId("settings-subscription-plan").isExisting();
    const hasCta = await byId("settings-choose-plan").isExisting();
    const hasRestart = await byId("settings-restart-checkout").isExisting();
    expect(hasPlan || hasCta || hasRestart).toBe(true);
  });

  it("billing screen shows the plan options", async () => {
    const cta = (await byId("settings-choose-plan").isExisting())
      ? "settings-choose-plan"
      : (await byId("settings-restart-checkout").isExisting())
        ? "settings-restart-checkout"
        : null;
    if (!cta) {
      console.log("SKIP: no billing CTA on settings (subscription state unknown)");
      return;
    }
    await tapId(cta);
    await waitForText("Choose your plan", 25000);
    await waitForId("plan-sole_trader", 15000);
    await waitForId("plan-pro", 15000);
    await waitForId("plan-team", 15000);
    await tapId("back-button", 8000);
    await waitForText("Settings", 15000);
  });

  it("business profile shows contact details persisted via the API", async () => {
    const row = textElContains("Business profile & branding");
    await row.waitForExist({ timeout: 15000 });
    await row.click();
    await waitForText("Branding", 15000);
    await driver.pause(500);
    // Render order on this screen: name, phone, address, custom hex.
    const fields = await (await $$("-ios class chain:**/XCUIElementTypeTextField")).getElements();
    expect(fields.length).toBeGreaterThanOrEqual(4);
    const name = await fieldValue(fields[0]);
    const phone = await fieldValue(fields[1]);
    const address = await fieldValue(fields[2]);
    expect(name.length).toBeGreaterThan(0);
    if (original.name) expect(name).toBe(original.name);
    if (original.phone) expect(phone).toBe(original.phone);
    if (original.address) expect(address).toBe(original.address);
    await tapId("back-button", 8000);
    await waitForText("Settings", 15000);
  });

  it("colour picker persists and survives a relaunch", async () => {
    const row = textElContains("Business profile & branding");
    await row.waitForExist({ timeout: 15000 });
    await row.click();
    await waitForText("Branding", 15000);
    const swatch = await $(`-ios predicate string:label == "Brand colour ${NEW_COLOUR}"`);
    await swatch.waitForExist({ timeout: 15000 });
    await swatch.click();
    // Hex input mirrors the picked swatch.
    const fields = await (await $$("-ios class chain:**/XCUIElementTypeTextField")).getElements();
    expect(await fieldValue(fields[3])).toBe(NEW_COLOUR);
    await tapId("branding-save", 25000);
    await driver.pause(800);

    const me = (await apiGet(ctx, "/tenants/me")) as TenantMe;
    expect(me.primaryColor?.toUpperCase()).toBe(NEW_COLOUR);
    colourChanged = true;

    // Re-open the branding screen after a fresh launch: the saved colour
    // must still be applied (fetched from the backend).
    await relaunchApp();
    await openTradeSettings();
    await waitForText("Settings", 15000);
    const rowAgain = textElContains("Business profile & branding");
    await rowAgain.waitForExist({ timeout: 15000 });
    await rowAgain.click();
    await waitForText("Branding", 15000);
    const relaunched = await (await $$("-ios class chain:**/XCUIElementTypeTextField")).getElements();
    expect(await fieldValue(relaunched[3])).toBe(NEW_COLOUR);
    await tapId("back-button", 8000);
  });

  it("logout returns to the entry screen", async () => {
    await waitForText("Settings", 15000);
    await tapId("settings-logout");
    // Logout lands on the role select (entry buttons live one tap deeper).
    await waitForId("role-select", 25000);
    await tapId("role-electrician");
    await waitForId("entry-trade-login", 15000);
    await tapId("back-button");
    await tapId("role-customer");
    await waitForId("entry-customer-login", 15000);
  });
});

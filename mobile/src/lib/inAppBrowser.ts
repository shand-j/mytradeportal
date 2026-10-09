import * as WebBrowser from "expo-web-browser";

/**
 * In-app browser helper — keeps customer payment flows inside the app instead
 * of bouncing to Safari (same pattern as useStripeConnectOnboarding). The
 * trade SaaS subscription is sold on the web (App Store Guideline 3.1.1), so
 * there is deliberately no checkout helper here.
 */

/**
 * Open a payment page that confirms in-page (e.g. the Stripe /pay page, whose
 * return flow is ?paid=1 on the same https URL — no mtp:// redirect) in a
 * plain in-app browser. There is no redirect to listen for, so the user
 * closes the sheet manually after paying.
 */
export async function openInAppBrowser(url: string): Promise<void> {
  await WebBrowser.openBrowserAsync(url);
}

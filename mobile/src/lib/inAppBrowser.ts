import * as WebBrowser from "expo-web-browser";

/**
 * In-app browser helpers — keep checkout/payment flows inside the app instead
 * of bouncing to Safari (same pattern as useStripeConnectOnboarding).
 */

/**
 * Open the Paddle checkout page (GET /billing/checkout-page?_ptxn=…) in an
 * ASWebAuthenticationSession. The page navigates to mtp:// on
 * checkout.completed, which auto-closes the sheet and lands the user back on
 * the screen that launched it. Resolves with "success" on the redirect and
 * "cancel"/"dismiss" when the user closes the sheet — none are errors, so
 * callers keep their existing post-open behavior (polling / advancing) in
 * every case.
 */
export async function openCheckoutSession(url: string): Promise<void> {
  await WebBrowser.openAuthSessionAsync(url, "mtp://");
}

/**
 * Open a payment page that confirms in-page (e.g. the Stripe /pay page, whose
 * return flow is ?paid=1 on the same https URL — no mtp:// redirect) in a
 * plain in-app browser. There is no redirect to listen for, so the user
 * closes the sheet manually after paying.
 */
export async function openInAppBrowser(url: string): Promise<void> {
  await WebBrowser.openBrowserAsync(url);
}

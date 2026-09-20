/**
 * Runtime configuration for the mobile app.
 *
 * `EXPO_PUBLIC_*` variables are inlined at build time by Expo. The app requires
 * a FastAPI backend; there is no offline demo mode.
 *
 * iOS simulator can reach the host's `localhost`; a physical device needs the
 * host LAN IP (set EXPO_PUBLIC_API_BASE_URL accordingly).
 */
const rawBaseUrl = process.env.EXPO_PUBLIC_API_BASE_URL?.trim() ?? "";

export const config = {
  /** Base URL of the FastAPI backend, e.g. http://localhost:8000. */
  apiBaseUrl: rawBaseUrl.replace(/\/$/, ""),
  /**
   * Setup token for the bootstrap tenant-creation endpoint (POST /tenants).
   * Required by the backend in production.
   */
  setupToken: process.env.EXPO_PUBLIC_SETUP_TOKEN?.trim() ?? "",
  /**
   * Business slug this (white-label) build targets. When set, the app fetches
   * that business's public white-label config on launch and themes itself for
   * the tenant. Empty = generic/marketplace build.
   */
  businessSlug: process.env.EXPO_PUBLIC_BUSINESS_SLUG?.trim() ?? "",
  /** Help centre on the marketing site — opened in the in-app browser. */
  helpUrl: "https://www.mytradeportal.co.uk/help",
};

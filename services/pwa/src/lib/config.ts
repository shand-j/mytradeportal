/**
 * Runtime configuration for the mobile app.
 *
 * `EXPO_PUBLIC_*` variables are inlined at build time by Expo. When an API base
 * URL is configured the app runs in "connected" mode against the real backend;
 * otherwise it stays in offline demo mode (mock data), so the marketing demo
 * and screenshots keep working with no backend.
 *
 * iOS simulator can reach the host's `localhost`; a physical device needs the
 * host LAN IP (set EXPO_PUBLIC_API_BASE_URL accordingly).
 */
const rawBaseUrl = process.env.EXPO_PUBLIC_API_BASE_URL?.trim() ?? "";

export const config = {
  /** Base URL of the FastAPI backend, e.g. http://localhost:8000. Empty = demo mode. */
  apiBaseUrl: rawBaseUrl.replace(/\/$/, ""),
  /**
   * Setup token for the bootstrap tenant-creation endpoint (POST /tenants).
   * Required by the backend in production; when empty, self-service business
   * registration stays in demo mode instead of hitting the real API.
   */
  setupToken: process.env.EXPO_PUBLIC_SETUP_TOKEN?.trim() ?? "",
  /**
   * Business slug this (white-label) build targets. When set in connected mode,
   * the app fetches that business's public white-label config on launch and
   * themes itself for the tenant. Empty = generic/marketplace build (demo).
   */
  businessSlug: process.env.EXPO_PUBLIC_BUSINESS_SLUG?.trim() ?? "",
  /** True when a backend is configured; gates real network calls vs mock data. */
  get apiEnabled(): boolean {
    return this.apiBaseUrl.length > 0;
  },
};

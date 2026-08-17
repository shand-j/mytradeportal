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
  /** True when a backend is configured; gates real network calls vs mock data. */
  get apiEnabled(): boolean {
    return this.apiBaseUrl.length > 0;
  },
};

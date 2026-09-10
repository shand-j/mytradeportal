/** Shared configuration constants for the E2E suite (overridable via env). */
export const DEVICE_UDID = process.env.IOS_UDID ?? "00008150-00186CE83A21401C";
export const BUNDLE_ID = "com.mytradeportal.mobile";
export const TEAM_ID = process.env.IOS_TEAM_ID ?? "LPDJH5X7V6";
export const API_BASE =
  process.env.MTP_API_BASE ?? "https://api-production-65db.up.railway.app";

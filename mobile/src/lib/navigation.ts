import { Linking, Platform } from "react-native";

/**
 * Build a turn-by-turn navigation URL for a destination, per platform:
 * iOS opens Apple Maps directions (`maps://?daddr=`), Android the geo: intent,
 * and web/anything else falls back to Google Maps directions in the browser.
 * Returns null when there is no address to navigate to.
 */
export function buildNavigationUrl(address?: string | null, postcode?: string | null): string | null {
  const query = [address, postcode]
    .map((part) => part?.trim() ?? "")
    .filter((part) => part.length > 0)
    .join(", ");
  if (!query) return null;
  const encoded = encodeURIComponent(query);
  if (Platform.OS === "ios") return `maps://?daddr=${encoded}`;
  if (Platform.OS === "android") return `geo:0,0?q=${encoded}`;
  return `https://www.google.com/maps/dir/?api=1&destination=${encoded}`;
}

/**
 * Open the platform maps app with directions to the destination. Falls back to
 * the Google Maps directions URL when the native scheme cannot be opened
 * (e.g. an Android emulator without a maps app). Returns false when there was
 * no address or no handler at all.
 */
export async function openNavigation(address?: string | null, postcode?: string | null): Promise<boolean> {
  const url = buildNavigationUrl(address, postcode);
  if (!url) return false;
  if (Platform.OS !== "web" && (await Linking.canOpenURL(url))) {
    await Linking.openURL(url);
    return true;
  }
  const query = [address, postcode]
    .map((part) => part?.trim() ?? "")
    .filter((part) => part.length > 0)
    .join(", ");
  const fallback = `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(query)}`;
  if (await Linking.canOpenURL(fallback)) {
    await Linking.openURL(fallback);
    return true;
  }
  return false;
}

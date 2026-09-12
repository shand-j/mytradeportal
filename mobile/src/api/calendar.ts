import { Linking, Platform, Share } from "react-native";
import { api } from "../lib/apiClient";

/** Response of GET /calendar/feed-link (camelized). */
export type CalendarFeedLink = {
  /** Plain https .ics feed URL — copy/share fallback and Google Calendar. */
  url: string;
  /** Same feed with a webcal:// scheme; opening it on iOS shows the native
   * "Subscribe to this calendar?" prompt instead of a raw link. */
  webcalUrl: string;
};

/** Fetch (minting on first use) this tenant's calendar feed URLs. */
export async function fetchCalendarFeedLink(): Promise<CalendarFeedLink> {
  return api.get<CalendarFeedLink>("/calendar/feed-link");
}

/**
 * Trigger the native add-to-calendar flow: on iOS open the webcal:// URL so
 * the OS subscribe prompt appears; elsewhere fall back to sharing the https
 * feed URL (e.g. for adding to Google Calendar by URL).
 */
export async function openCalendarSubscription(): Promise<void> {
  const link = await fetchCalendarFeedLink();
  if (Platform.OS === "ios" && (await Linking.canOpenURL(link.webcalUrl))) {
    await Linking.openURL(link.webcalUrl);
    return;
  }
  await Share.share({ message: link.url });
}

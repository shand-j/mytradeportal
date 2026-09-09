import { useEffect } from "react";
import { Platform } from "react-native";
import { useRouter } from "expo-router";
import { useQueryClient } from "@tanstack/react-query";
import {
  GENERATING_POLL_MS,
  NOTIFICATIONS_POLL_MS,
  NotificationRole,
  quoteIdFromLink,
  routeForNotificationLink,
  useQuoteReadyWatcher,
} from "../../api/notifications";
import {
  requestFirstLaunchPermissions,
  setupNotificationHandler,
} from "../../lib/pushNotifications";
import { useQuoteGenerationStore } from "../../stores/quoteGenerationStore";

/**
 * Mounted once per authenticated role (in the route-group layout). Sets up
 * the local-notification handler, runs the first-launch permission/push-token
 * flow, watches for quote_ready/quote_failed notifications — firing local
 * alerts and updating the async quote-generation banner state — and routes
 * taps on system push notifications to the linked in-app screen.
 */
export function NotificationWatcher({ role }: { role: NotificationRole }) {
  const queryClient = useQueryClient();
  const router = useRouter();
  const phase = useQuoteGenerationStore((s) => s.phase);

  useEffect(() => {
    void setupNotificationHandler();
    void requestFirstLaunchPermissions(role);
  }, [role]);

  // Deep-link taps on system push notifications (app backgrounded or killed).
  // The backend sends the notification link in the push payload's `data`.
  useEffect(() => {
    if (Platform.OS === "web") return;
    let cancelled = false;
    let subscription: { remove: () => void } | undefined;
    void (async () => {
      const Notifications = await import("expo-notifications");
      if (cancelled) return;
      const follow = (link: unknown) => {
        const target = routeForNotificationLink(role, typeof link === "string" ? link : null);
        if (target) router.push(target as never);
      };
      const last = await Notifications.getLastNotificationResponseAsync();
      if (last) {
        follow((last.notification.request.content.data as { link?: unknown })?.link);
      }
      subscription = Notifications.addNotificationResponseReceivedListener((response) => {
        follow((response.notification.request.content.data as { link?: unknown })?.link);
      });
    })();
    return () => {
      cancelled = true;
      subscription?.remove();
    };
  }, [role, router]);

  useQuoteReadyWatcher(
    role,
    (notification) => {
      if (notification.type === "quote_ready") {
        useQuoteGenerationStore.getState().markReady(quoteIdFromLink(notification.link));
      } else if (notification.type === "quote_failed") {
        useQuoteGenerationStore.getState().markFailed();
      }
      // A generated/updated quote changes the leads + quotes lists.
      queryClient.invalidateQueries({ queryKey: ["quotes"] });
      queryClient.invalidateQueries({ queryKey: ["quote-requests"] });
      queryClient.invalidateQueries({ queryKey: ["my-quotes"] });
      queryClient.invalidateQueries({ queryKey: ["my-requests"] });
    },
    phase === "generating" ? GENERATING_POLL_MS : NOTIFICATIONS_POLL_MS
  );

  return null;
}

import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  GENERATING_POLL_MS,
  NOTIFICATIONS_POLL_MS,
  NotificationRole,
  quoteIdFromLink,
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
 * flow, and watches for quote_ready/quote_failed notifications — firing local
 * alerts and updating the async quote-generation banner state.
 */
export function NotificationWatcher({ role }: { role: NotificationRole }) {
  const queryClient = useQueryClient();
  const phase = useQuoteGenerationStore((s) => s.phase);

  useEffect(() => {
    void setupNotificationHandler();
    void requestFirstLaunchPermissions(role);
  }, [role]);

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

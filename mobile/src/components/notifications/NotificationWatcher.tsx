import { useEffect, useRef } from "react";
import { AppState, Platform } from "react-native";
import { useRouter } from "expo-router";
import { useQueryClient } from "@tanstack/react-query";
import {
  GENERATING_POLL_MS,
  NOTIFICATIONS_POLL_MS,
  NotificationRole,
  quoteIdFromLink,
  routeForPushData,
  useQuoteReadyWatcher,
} from "../../api/notifications";
import { dedupeKey, markRemotePushDelivered } from "../../lib/notificationDedupe";
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
 *
 * Dedupe contract with the local quote-ready fallback: a remote push that is
 * received in the foreground or tapped is marked delivered for its entity, so
 * the polled fallback never re-alerts for the same event — and each tap is
 * routed exactly once.
 */
export function NotificationWatcher({ role }: { role: NotificationRole }) {
  const queryClient = useQueryClient();
  const router = useRouter();
  // The listeners below are registered once per role; route through a ref so
  // an unstable useRouter() identity never re-triggers registration.
  const routerRef = useRef(router);
  routerRef.current = router;
  const phase = useQuoteGenerationStore((s) => s.phase);

  useEffect(() => {
    void setupNotificationHandler();
    void requestFirstLaunchPermissions(role);
    // Token registration is idempotent and retries on every call, so re-run
    // it on each foregrounding: a registration that failed at cold start
    // (backend unreachable, token churn after an OTA update) recovers without
    // waiting for the next app launch.
    const sub = AppState.addEventListener("change", (state) => {
      if (state === "active") void requestFirstLaunchPermissions(role);
    });
    return () => sub.remove();
  }, [role]);

  // Deep-link taps on system push notifications (app backgrounded or killed).
  // The backend sends { type, id, link } in the push payload's `data`; taps
  // resolve through the same route map as the in-app notification list.
  useEffect(() => {
    if (Platform.OS === "web") return;
    let cancelled = false;
    let responseSubscription: { remove: () => void } | undefined;
    let receivedSubscription: { remove: () => void } | undefined;
    void (async () => {
      const Notifications = await import("expo-notifications");
      if (cancelled) return;

      const keyForData = (data: unknown) => {
        const payload = data as { link?: unknown; type?: unknown; id?: unknown } | undefined;
        return dedupeKey(
          typeof payload?.type === "string" ? payload.type : null,
          typeof payload?.link === "string" ? payload.link : null,
          typeof payload?.id === "string" ? payload.id : null
        );
      };

      // A push that arrived in the foreground presents itself via the
      // notification handler — mark it delivered so the polled local fallback
      // does not stack a second banner for the same entity.
      receivedSubscription = Notifications.addNotificationReceivedListener((notification) => {
        markRemotePushDelivered(keyForData(notification.request.content.data));
      });

      // The app-opening tap surfaces via BOTH getLastNotificationResponseAsync
      // and the response listener — route each tap once, by request id.
      const handledResponseIds = new Set<string>();
      const handleResponse = (response: import("expo-notifications").NotificationResponse) => {
        const identifier = response.notification.request.identifier;
        if (handledResponseIds.has(identifier)) return;
        handledResponseIds.add(identifier);
        const data = response.notification.request.content.data;
        markRemotePushDelivered(keyForData(data));
        const target = routeForPushData(
          role,
          data as { link?: unknown; type?: unknown; id?: unknown }
        );
        if (target) routerRef.current.push(target as never);
      };
      responseSubscription = Notifications.addNotificationResponseReceivedListener(handleResponse);

      const last = await Notifications.getLastNotificationResponseAsync();
      if (cancelled) return;
      if (last) {
        handleResponse(last);
        // Consume the stale response: without clearing, every remount or
        // effect re-run would re-route (and re-suppress) for an old tap.
        try {
          Notifications.clearLastNotificationResponse();
        } catch {
          // Native builds lacking the clear API keep the once-per-mount guard.
        }
      }
    })();
    return () => {
      cancelled = true;
      responseSubscription?.remove();
      receivedSubscription?.remove();
    };
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

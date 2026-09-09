import { useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Platform } from "react-native";
import { api } from "../lib/apiClient";
import { fireLocalQuoteReadyAlert } from "../lib/pushNotifications";
import { useAuthStore } from "../stores/authStore";

export type NotificationRole = "trade" | "customer";

/** Camelized NotificationRead from the backend. */
export type AppNotification = {
  id: string;
  recipientType: string;
  recipientId: string;
  /** e.g. "quote_ready" (link `/quotes/{id}`) or "quote_failed". */
  type: string;
  title: string;
  body: string | null;
  link: string | null;
  readAt: string | null;
  createdAt: string;
};

function basePath(role: NotificationRole): string {
  return role === "customer" ? "/customer/notifications" : "/notifications";
}

/** List notifications for the authenticated user (staff or customer). */
export async function fetchNotifications(role: NotificationRole): Promise<AppNotification[]> {
  return api.get<AppNotification[]>(basePath(role));
}

/** Mark a notification as read. */
export async function markNotificationRead(role: NotificationRole, id: string): Promise<void> {
  await api.patch(`${basePath(role)}/${id}/read`);
}

type UnreadCountResponse = { count?: number; unreadCount?: number };

/** Unread notification count for the bell badge. */
export async function fetchUnreadCount(role: NotificationRole): Promise<number> {
  const data = await api.get<UnreadCountResponse>(`${basePath(role)}/unread-count`);
  return data.unreadCount ?? data.count ?? 0;
}

/**
 * Register the Expo push token with the backend. Tolerates failure — the
 * simulator has no push capability, so callers fire-and-forget this.
 */
export async function registerPushToken(
  role: NotificationRole,
  token: string,
  platform: string
): Promise<void> {
  await api.post(`${basePath(role)}/push-token`, { token, platform });
}

/** Report a device-side diagnostic line to the server log pipeline. */
export async function reportClientLog(
  message: string,
  context: Record<string, unknown> = {}
): Promise<void> {
  await api.post("/diagnostics/client-log", { message, context });
}

/** Default poll interval for notification queries. */
export const NOTIFICATIONS_POLL_MS = 30_000;
/** Faster poll while an async quote generation is in flight. */
export const GENERATING_POLL_MS = 15_000;

/** Notifications list, polled so the bell badge and quote-ready alerts stay fresh. */
export function useNotifications(role: NotificationRole, refetchInterval = NOTIFICATIONS_POLL_MS) {
  // Only fire once the auth store has a signed-in user of the matching role,
  // otherwise the query races the login flow and 401s immediately after
  // login — the toast then blocks the notifications screen from ever
  // recovering without a full app reload.
  const authRole = useAuthStore((state) => state.role);
  const user = useAuthStore((state) => state.user);
  const isReady =
    user !== null && (role === "trade" ? authRole === "trade" : authRole === "customer");
  return useQuery({
    queryKey: ["notifications", role],
    queryFn: () => fetchNotifications(role),
    refetchInterval,
    enabled: isReady,
  });
}

/** Unread count for the bell badge, polled. */
export function useUnreadCount(role: NotificationRole) {
  const authRole = useAuthStore((state) => state.role);
  const user = useAuthStore((state) => state.user);
  const isReady =
    user !== null && (role === "trade" ? authRole === "trade" : authRole === "customer");
  return useQuery({
    queryKey: ["notifications", role, "unread-count"],
    queryFn: () => fetchUnreadCount(role),
    refetchInterval: NOTIFICATIONS_POLL_MS,
    enabled: isReady,
  });
}

/** Mutation: mark a notification read and refresh the notification caches. */
export function useMarkNotificationRead(role: NotificationRole) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => markNotificationRead(role, id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["notifications", role] });
    },
  });
}

/** Extract the quote id from a quote_ready link like `/quotes/{id}`. */
export function quoteIdFromLink(link: string | null | undefined): string | null {
  if (!link) return null;
  const match = link.match(/\/quotes\/([0-9a-f-]+)/i);
  return match ? match[1] : null;
}

/** In-app route for a notification link, per role (null when unmapped). */
export function routeForNotificationLink(
  role: NotificationRole,
  link: string | null | undefined
): { pathname: string; params?: Record<string, string> } | null {
  const chatMatch = link?.match(/\/chat\/([0-9a-f-]+)/i);
  if (chatMatch) {
    // Chat links open the thread directly on either side (the customer chat
    // link is `/customer/chat/{quoteRequestId}` — same tail match).
    const pathname = role === "trade" ? "/(trade)/messages" : "/(customer)/messages";
    return { pathname, params: { quoteRequestId: chatMatch[1] } };
  }
  if (role === "trade") {
    const quoteId = quoteIdFromLink(link);
    if (quoteId) return { pathname: `/(trade)/quote/${quoteId}` };
    const leadMatch = link?.match(/\/quote-requests\/([0-9a-f-]+)/i);
    if (leadMatch) return { pathname: `/(trade)/lead/${leadMatch[1]}` };
    return null;
  }
  // Customer quotes are reviewed inline on the requests screen.
  if (quoteIdFromLink(link) || link?.startsWith("/quotes")) {
    return { pathname: "/(customer)/requests" };
  }
  return null;
}

/**
 * Foreground quote alerts: polls notifications and fires a local
 * expo-notifications alert when a NEW unread quote_ready notification appears
 * while the app is open. Also reports freshly arrived quote_ready/quote_failed
 * notifications so callers can react (e.g. update the "generating" banner).
 */
export function useQuoteReadyWatcher(
  role: NotificationRole,
  onQuoteEvent?: (notification: AppNotification) => void,
  refetchInterval: number = NOTIFICATIONS_POLL_MS
) {
  const query = useNotifications(role, refetchInterval);
  const seenRef = useRef<Set<string> | null>(null);
  const callbackRef = useRef(onQuoteEvent);
  callbackRef.current = onQuoteEvent;

  useEffect(() => {
    const notifications = query.data;
    if (!notifications) return;
    const unreadQuoteEvents = notifications.filter(
      (n) => (n.type === "quote_ready" || n.type === "quote_failed") && !n.readAt
    );
    if (seenRef.current === null) {
      // First load: don't alert for notifications that predate app launch.
      seenRef.current = new Set(unreadQuoteEvents.map((n) => n.id));
      return;
    }
    const fresh = unreadQuoteEvents.filter((n) => !seenRef.current!.has(n.id));
    if (fresh.length === 0) return;
    fresh.forEach((n) => {
      seenRef.current!.add(n.id);
      if (n.type === "quote_ready" && Platform.OS !== "web") {
        void fireLocalQuoteReadyAlert(n.title, n.body ?? "");
      }
      callbackRef.current?.(n);
    });
  }, [query.data]);
}

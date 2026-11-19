import { useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Platform } from "react-native";
import { api } from "../lib/apiClient";
import { dedupeKey, shouldFireLocalAlert } from "../lib/notificationDedupe";
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

/** Mark every visible notification as read; returns how many were marked. */
export async function markAllNotificationsRead(role: NotificationRole): Promise<number> {
  const data = await api.post<{ markedRead: number }>(`${basePath(role)}/read-all`);
  return data.markedRead;
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

/** Mutation: mark all visible notifications read and refresh the caches. */
export function useMarkAllNotificationsRead(role: NotificationRole) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => markAllNotificationsRead(role),
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

function idFromLink(link: string | null | undefined, pattern: RegExp): string | null {
  const match = link?.match(pattern);
  return match ? match[1] : null;
}

/** In-app route for a notification link, per role (null when unmapped). */
export function routeForNotificationLink(
  role: NotificationRole,
  link: string | null | undefined,
  type?: string | null
): { pathname: string; params?: Record<string, string> } | null {
  const chatId = idFromLink(link, /\/chat\/([0-9a-f-]+)/i);
  if (chatId) {
    // Chat links open the thread directly on either side (the customer chat
    // link is `/customer/chat/{quoteRequestId}` — same tail match).
    const pathname = role === "trade" ? "/(trade)/messages" : "/(customer)/messages";
    return { pathname, params: { quoteRequestId: chatId } };
  }
  // Quote links: canonical `/quotes/{id}`; older rows may carry `/quote/{id}`
  // or `/customer/quote/{id}` — all open the same quote.
  const quoteId = idFromLink(link, /\/quotes?\/([0-9a-f-]+)/i);
  if (role === "trade") {
    if (quoteId) return { pathname: `/(trade)/quote/${quoteId}` };
    const jobId = idFromLink(link, /\/jobs?\/([0-9a-f-]+)/i);
    if (jobId) return { pathname: `/(trade)/job/${jobId}` };
    const invoiceId = idFromLink(link, /\/invoices\/([0-9a-f-]+)/i);
    if (invoiceId) return { pathname: `/(trade)/invoice/${invoiceId}` };
    const leadId = idFromLink(link, /\/quote-requests\/([0-9a-f-]+)/i);
    if (leadId) return { pathname: `/(trade)/lead/${leadId}` };
    return null;
  }
  // Customer invoice links open the new invoice screens: `/customer/invoice/{id}`
  // (invoice_sent rows) or `/invoices/{id}` (rebuilt push-payload links). An
  // invoice type without a parseable id falls back to the list.
  const invoiceId = idFromLink(link, /\/invoices?\/([0-9a-f-]+)/i);
  if (invoiceId) return { pathname: `/(customer)/invoice/${invoiceId}` };
  if (type?.startsWith("invoice")) return { pathname: "/(customer)/invoices" };
  // Customer quotes are reviewed inline on the requests screen.
  if (quoteId || type?.startsWith("quote")) {
    return { pathname: "/(customer)/requests" };
  }
  return null;
}

/** Rebuild a notification link from a push payload's `type` + `id` when `link` is absent. */
export function linkFromPushData(
  type: string | null | undefined,
  id: string | null | undefined
): string | null {
  if (!type || !id) return null;
  switch (type) {
    case "quote_ready":
    case "quote_sent":
    case "quote_accepted":
      return `/quotes/${id}`;
    case "chat_reply":
    case "chat_message":
      return `/chat/${id}`;
    case "job_scheduled":
      return `/job/${id}`;
    case "invoice_paid":
    case "invoice_sent":
      return `/invoices/${id}`;
    default:
      return null;
  }
}

/**
 * Route for a system-push tap: prefers the payload's `link`, falls back to
 * reconstructing one from `type` + `id`, and resolves through the same map
 * as the in-app notification list so both entry points land identically.
 */
export function routeForPushData(
  role: NotificationRole,
  data: { link?: unknown; type?: unknown; id?: unknown } | null | undefined
): { pathname: string; params?: Record<string, string> } | null {
  const link = typeof data?.link === "string" && data.link ? data.link : null;
  const type = typeof data?.type === "string" ? data.type : null;
  const id = typeof data?.id === "string" ? data.id : null;
  return routeForNotificationLink(role, link ?? linkFromPushData(type, id), type);
}

/**
 * Foreground quote alerts: polls notifications and fires a local
 * expo-notifications alert when a NEW unread quote_ready notification appears
 * while the app is open. Also reports freshly arrived quote_ready/quote_failed
 * notifications so callers can react (e.g. update the "generating" banner).
 * The local alert is skipped when the remote push for the same entity was
 * already received or tapped this session, and fires at most once per entity
 * per session (see src/lib/notificationDedupe.ts).
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
      if (
        n.type === "quote_ready" &&
        Platform.OS !== "web" &&
        shouldFireLocalAlert(dedupeKey(n.type, n.link))
      ) {
        void fireLocalQuoteReadyAlert(n.title, n.body ?? "");
      }
      callbackRef.current?.(n);
    });
  }, [query.data]);
}

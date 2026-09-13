import { Pressable, ScrollView, View } from "react-native";
import { useRouter } from "expo-router";
import { Header } from "../../components/ui/Header";
import { Icon, IconName } from "../../components/ui/Icon";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import {
  AppNotification,
  NotificationRole,
  routeForNotificationLink,
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
  useNotifications,
} from "../../api/notifications";
import { formatDateUK } from "../../lib/format";

const TYPE_ICONS: Record<string, IconName> = {
  quote_ready: "sparkles",
  quote_sent: "sparkles",
  quote_accepted: "circle-check",
  quote_failed: "warning",
  chat_reply: "message",
  chat_message: "message",
  triage_closed: "message",
  job_scheduled: "calendar",
  invoice_sent: "document",
  invoice_paid: "circle-check",
};

function iconFor(type: string): IconName {
  return TYPE_ICONS[type] ?? "info";
}

export type NotificationsScreenProps = {
  role: NotificationRole;
  onBack: () => void;
};

/** Notification inbox for one role: unread highlighted, tap marks read + deep-links. */
export function NotificationsScreen({ role, onBack }: NotificationsScreenProps) {
  const router = useRouter();
  const { data: notifications, isLoading } = useNotifications(role);
  const markRead = useMarkNotificationRead(role);
  const markAllRead = useMarkAllNotificationsRead(role);
  const hasUnread = (notifications ?? []).some((n) => !n.readAt);

  const openNotification = (notification: AppNotification) => {
    if (!notification.readAt) {
      markRead.mutate(notification.id);
    }
    // Unresolvable targets (e.g. quote_failed, customer invoices) navigate
    // nowhere — the row just marks read instead of erroring.
    const target = routeForNotificationLink(role, notification.link, notification.type);
    if (target) {
      router.push(target as never);
    }
  };

  return (
    <Screen>
      <Header
        testID="notifications-back"
        title="Notifications"
        onBack={onBack}
        rightAction={
          hasUnread ? (
            <Pressable
              testID="notifications-mark-all-read"
              disabled={markAllRead.isPending}
              onPress={() => markAllRead.mutate()}
              hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
            >
              <Text variant="caption" weight="semibold" color="secondary">
                {markAllRead.isPending ? "Marking…" : "Mark all read"}
              </Text>
            </Pressable>
          ) : null
        }
      />

      <ScrollView className="flex-1" contentContainerClassName="gap-3 pb-6">
        {isLoading && (
          <Text variant="caption" color="secondary" align="center">
            Loading notifications…
          </Text>
        )}

        {!isLoading && (notifications ?? []).length === 0 && (
          <View className="gap-2 rounded-2xl bg-gray-100 p-6">
            <Text variant="body" align="center" color="secondary">
              No notifications yet.
            </Text>
            <Text variant="caption" align="center" color="secondary">
              We'll let you know here when a quote is ready.
            </Text>
          </View>
        )}

        {(notifications ?? []).map((notification) => {
          const unread = !notification.readAt;
          return (
            <Pressable
              key={notification.id}
              testID={`notification-${notification.id}`}
              onPress={() => openNotification(notification)}
            >
              <View
                className={`flex-row items-start gap-3 rounded-2xl border p-4 ${
                  unread ? "border-primary-200 bg-primary-50" : "border-gray-200 bg-white"
                }`}
              >
                <View
                  className={`h-9 w-9 items-center justify-center rounded-full ${
                    notification.type === "quote_failed" ? "bg-amber-100" : "bg-primary-100"
                  }`}
                >
                  <Icon
                    name={iconFor(notification.type)}
                    size={18}
                    color={notification.type === "quote_failed" ? "#B45309" : "#0F1E26"}
                  />
                </View>
                <View className="flex-1 gap-0.5">
                  <Text variant="body" weight={unread ? "semibold" : "normal"}>
                    {notification.title}
                  </Text>
                  {notification.body ? (
                    <Text variant="caption" color="secondary">
                      {notification.body}
                    </Text>
                  ) : null}
                  <Text variant="caption" color="secondary">
                    {formatDateUK(notification.createdAt)}
                  </Text>
                </View>
                {unread && <View className="mt-1.5 h-2 w-2 rounded-full bg-accent-500" />}
              </View>
            </Pressable>
          );
        })}
      </ScrollView>
    </Screen>
  );
}

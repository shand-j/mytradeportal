import { Pressable, ScrollView, View } from "react-native";
import { useRouter } from "expo-router";
import { Header } from "../../components/ui/Header";
import { Icon, IconName } from "../../components/ui/Icon";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import {
  AppNotification,
  NotificationRole,
  quoteIdFromLink,
  useMarkNotificationRead,
  useNotifications,
} from "../../api/notifications";
import { formatDateUK } from "../../lib/format";

const TYPE_ICONS: Record<string, IconName> = {
  quote_ready: "sparkles",
  quote_failed: "warning",
};

function iconFor(type: string): IconName {
  return TYPE_ICONS[type] ?? "info";
}

export type NotificationsScreenProps = {
  role: NotificationRole;
  onBack: () => void;
};

/** Notification inbox for one role: unread highlighted, tap marks read + follows the link. */
export function NotificationsScreen({ role, onBack }: NotificationsScreenProps) {
  const router = useRouter();
  const { data: notifications, isLoading } = useNotifications(role);
  const markRead = useMarkNotificationRead(role);

  const openNotification = (notification: AppNotification) => {
    if (!notification.readAt) {
      markRead.mutate(notification.id);
    }
    const quoteId = quoteIdFromLink(notification.link);
    if (role === "trade") {
      if (quoteId) {
        router.push(`/(trade)/quote/${quoteId}`);
      } else {
        const leadMatch = notification.link?.match(/\/quote-requests\/([0-9a-f-]+)/i);
        if (leadMatch) router.push(`/(trade)/lead/${leadMatch[1]}`);
      }
    } else if (quoteId || notification.type.startsWith("quote")) {
      // Customer quotes are reviewed inline on the requests screen.
      router.push("/(customer)/requests");
    }
  };

  return (
    <Screen>
      <Header testID="notifications-back" title="Notifications" onBack={onBack} />

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
                  unread ? "border-blue-200 bg-blue-50" : "border-gray-200 bg-white"
                }`}
              >
                <View
                  className={`h-9 w-9 items-center justify-center rounded-full ${
                    notification.type === "quote_failed" ? "bg-amber-100" : "bg-blue-100"
                  }`}
                >
                  <Icon
                    name={iconFor(notification.type)}
                    size={18}
                    color={notification.type === "quote_failed" ? "#B45309" : "#2563EB"}
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
                {unread && <View className="mt-1.5 h-2 w-2 rounded-full bg-blue-600" />}
              </View>
            </Pressable>
          );
        })}
      </ScrollView>
    </Screen>
  );
}

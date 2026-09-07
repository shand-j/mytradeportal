import { Pressable, View } from "react-native";
import { useRouter } from "expo-router";
import { Icon } from "../ui/Icon";
import { Text } from "../ui/Text";
import { NotificationRole, useUnreadCount } from "../../api/notifications";

/**
 * Bell with an unread-count badge for screen headers. Tapping opens the
 * notifications screen for the given role.
 */
export function NotificationBell({ role, testID }: { role: NotificationRole; testID?: string }) {
  const router = useRouter();
  const { data: unread } = useUnreadCount(role);
  const route = role === "customer" ? "/(customer)/notifications" : "/(trade)/notifications";

  return (
    <Pressable
      testID={testID ?? `notifications-bell-${role}`}
      onPress={() => router.push(route as never)}
      accessibilityLabel="Notifications"
      hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
    >
      <View>
        <Icon name="notifications" size={24} color="#374151" />
        {(unread ?? 0) > 0 && (
          <View
            testID="notifications-badge"
            className="absolute -top-1 -right-1 min-w-[16px] items-center rounded-full bg-red-500 px-1"
          >
            <Text variant="caption" style={{ color: "#FFFFFF", fontSize: 9 }} weight="bold">
              {unread! > 99 ? "99+" : String(unread)}
            </Text>
          </View>
        )}
      </View>
    </Pressable>
  );
}

import { Stack, usePathname } from "expo-router";
import { View } from "react-native";
import { BottomTabBar } from "../../src/components/navigation/BottomTabBar";
import { NotificationWatcher } from "../../src/components/notifications/NotificationWatcher";

// usePathname returns the path without route-group segments, e.g. "/requests"
// — including "(customer)" here would never match and the tab bar would never
// render.
const MAIN_CUSTOMER_ROUTES = ["/requests", "/calendar", "/messages", "/profile"];

export default function CustomerLayout() {
  const pathname = usePathname();
  const showTabBar = MAIN_CUSTOMER_ROUTES.includes(pathname);

  return (
    <View className="flex-1">
      <NotificationWatcher role="customer" />
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Screen name="requests" />
        <Stack.Screen name="calendar" />
        <Stack.Screen name="messages" />
        <Stack.Screen name="profile" />
        <Stack.Screen name="notifications" />
      </Stack>
      {showTabBar && <BottomTabBar variant="customer" />}
    </View>
  );
}

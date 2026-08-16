import { Stack, usePathname } from "expo-router";
import { View } from "react-native";
import { BottomTabBar } from "../../src/components/navigation/BottomTabBar";

const MAIN_CUSTOMER_ROUTES = [
  "/(customer)/requests",
  "/(customer)/calendar",
  "/(customer)/messages",
  "/(customer)/profile",
];

export default function CustomerLayout() {
  const pathname = usePathname();
  const showTabBar = MAIN_CUSTOMER_ROUTES.includes(pathname);

  return (
    <View className="flex-1">
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Screen name="requests" />
        <Stack.Screen name="calendar" />
        <Stack.Screen name="messages" />
        <Stack.Screen name="profile" />
      </Stack>
      {showTabBar && <BottomTabBar variant="customer" />}
    </View>
  );
}

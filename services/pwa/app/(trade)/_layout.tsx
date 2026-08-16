import { Stack, usePathname } from "expo-router";
import { View } from "react-native";
import { BottomTabBar } from "../../src/components/navigation/BottomTabBar";

export default function TradeLayout() {
  const showTabBar = true;

  return (
    <View className="flex-1">
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Screen name="dashboard" />
        <Stack.Screen name="quotes" />
        <Stack.Screen name="customers" />
        <Stack.Screen name="calendar" />
        <Stack.Screen name="leads" />
        <Stack.Screen name="lead/[id]" />
        <Stack.Screen name="quote/[id]" />
        <Stack.Screen name="quote-intake" />
        <Stack.Screen name="request-info" />
        <Stack.Screen name="job/[id]" />
        <Stack.Screen name="invoice/[id]" />
        <Stack.Screen name="analytics" />
        <Stack.Screen name="branding" />
        <Stack.Screen name="follow-ups" />
        <Stack.Screen name="manual-lead" />
        <Stack.Screen name="settings" />
      </Stack>
      {showTabBar && <BottomTabBar variant="trade" />}
    </View>
  );
}

import { Stack, useRouter } from "expo-router";
import { useEffect } from "react";
import { View } from "react-native";
import { BottomTabBar } from "../../src/components/navigation/BottomTabBar";
import { NotificationWatcher } from "../../src/components/notifications/NotificationWatcher";
import { usePaywallStore } from "../../src/stores/paywallStore";

export default function TradeLayout() {
  const showTabBar = true;
  const router = useRouter();
  const paywallRequired = usePaywallStore((s) => s.required);

  // Global billing enforcement. index.tsx only routes to /paywall when a 402
  // lands before it unmounts; a canceled tenant's first gated call 402s after
  // the dashboard has mounted (and route restoration skips index entirely), so
  // the gate lives here — it stays mounted for every trade screen and sends
  // the user to /paywall the moment any API call sets the flag.
  useEffect(() => {
    if (paywallRequired) {
      router.replace("/paywall");
    }
  }, [paywallRequired, router]);

  return (
    <View className="flex-1">
      <NotificationWatcher role="trade" />
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Screen name="dashboard" />
        <Stack.Screen name="quotes" />
        <Stack.Screen name="customers" />
        <Stack.Screen name="calendar" />
        <Stack.Screen name="inbox" />
        <Stack.Screen name="lead/[id]" />
        <Stack.Screen name="customer/[id]" />
        <Stack.Screen name="quote/[id]" />
        <Stack.Screen name="quote-intake" />
        <Stack.Screen name="request-info" />
        <Stack.Screen name="job/[id]" />
        <Stack.Screen name="job/new" />
        <Stack.Screen name="invoice/[id]" />
        <Stack.Screen name="invoice/new" />
        <Stack.Screen name="analytics" />
        <Stack.Screen name="invoices" />
        <Stack.Screen name="branding" />
        <Stack.Screen name="payment-details" />
        <Stack.Screen name="follow-ups" />
        <Stack.Screen name="manual-lead" />
        <Stack.Screen name="certificates" />
        <Stack.Screen name="certificate/[id]" />
        <Stack.Screen name="settings" />
        <Stack.Screen name="notifications" />
      </Stack>
      {showTabBar && <BottomTabBar variant="trade" />}
    </View>
  );
}

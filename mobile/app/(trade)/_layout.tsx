import { Stack, useRouter } from "expo-router";
import { useEffect } from "react";
import { View } from "react-native";
import { BottomTabBar } from "../../src/components/navigation/BottomTabBar";
import { NotificationWatcher } from "../../src/components/notifications/NotificationWatcher";
import { usePaywallStore } from "../../src/stores/paywallStore";
import { useFeatureFlags } from "../../src/api/featureFlags";
import { useAuth } from "../../src/contexts/AuthContext";

export default function TradeLayout() {
  const showTabBar = true;
  const router = useRouter();
  const { role, user, sessionRestored } = useAuth();
  const paywallRequired = usePaywallStore((s) => s.required);
  const { data: featureFlags } = useFeatureFlags();
  const paddleBillingEnabled = featureFlags?.paddleBilling === true;
  const isAuthenticatedTradeUser = role === "trade" && user !== null;

  useEffect(() => {
    if (sessionRestored && !isAuthenticatedTradeUser) {
      router.replace("/");
    }
  }, [sessionRestored, isAuthenticatedTradeUser, router]);

  // Global billing enforcement. index.tsx only routes to /paywall when a 402
  // lands before it unmounts; an inactive tenant's first gated call 402s after
  // the dashboard has mounted (and route restoration skips index entirely), so
  // the gate lives here — it stays mounted for every trade screen and sends
  // the user to /paywall the moment any API call sets the flag.
  useEffect(() => {
    if (isAuthenticatedTradeUser && paddleBillingEnabled && paywallRequired) {
      router.replace("/paywall");
    }
  }, [isAuthenticatedTradeUser, paywallRequired, paddleBillingEnabled, router]);

  if (!sessionRestored || !isAuthenticatedTradeUser) {
    return <View className="flex-1" />;
  }

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
        <Stack.Screen name="settings" />
        <Stack.Screen name="notifications" />
      </Stack>
      {showTabBar && <BottomTabBar variant="trade" />}
    </View>
  );
}

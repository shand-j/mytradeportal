import { useRouter } from "expo-router";
import { useState } from "react";
import { Pressable, ScrollView, Share, View } from "react-native";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { useAuth } from "../../contexts/AuthContext";
import { useBusiness } from "../../theme/ThemeProvider";
import { useSubscription } from "../../api/billing";

function SubscriptionCard() {
  const { data, isLoading } = useSubscription();
  const router = useRouter();

  if (isLoading) {
    return null;
  }

  const openPlanPicker = () => router.push("/(trade)/billing");

  if (!data) {
    return (
      <View className="rounded-2xl bg-slate-100 p-4 gap-2">
        <Text variant="body" weight="semibold">
          Subscription
        </Text>
        <Text variant="caption" color="secondary">
          You don't have an active plan yet. Start a 14-day free trial to unlock everything.
        </Text>
        <Button testID="settings-choose-plan" title="Choose a plan" onPress={openPlanPicker} />
      </View>
    );
  }

  const trialLeft =
    data.status === "trialing" && data.trialEndsAt
      ? `Trial ends ${new Date(data.trialEndsAt).toLocaleDateString("en-GB", {
          day: "numeric",
          month: "short",
        })}`
      : null;
  const renewsAt =
    (data.status === "active" || data.status === "past_due") && data.currentPeriodEnd
      ? `Renews ${new Date(data.currentPeriodEnd).toLocaleDateString("en-GB", {
          day: "numeric",
          month: "short",
        })}`
      : null;
  const statusLabel: Record<string, string> = {
    incomplete: "Setup incomplete",
    trialing: "Free trial",
    active: "Active",
    past_due: "Payment past due",
    paused: "Paused",
    canceled: "Cancelled",
  };
  const planLabel = data.planKey.charAt(0).toUpperCase() + data.planKey.slice(1);

  return (
    <View className="rounded-2xl bg-slate-100 p-4 gap-2">
      <View className="flex-row items-center justify-between">
        <Text variant="body" weight="semibold">
          Subscription
        </Text>
        <View className="rounded-full bg-white px-2 py-0.5">
          <Text testID="settings-subscription-status" variant="caption" weight="semibold">
            {statusLabel[data.status] ?? data.status}
          </Text>
        </View>
      </View>
      <Text testID="settings-subscription-plan" variant="body">
        {planLabel} plan
      </Text>
      {trialLeft && (
        <Text variant="caption" color="secondary">
          {trialLeft}
        </Text>
      )}
      {renewsAt && (
        <Text variant="caption" color="secondary">
          {renewsAt}
        </Text>
      )}
      {data.status === "incomplete" && (
        <Text variant="caption" color="warning">
          Checkout wasn't completed — try again to finish activating your plan.
        </Text>
      )}
      {(data.status === "incomplete" || data.status === "canceled") && (
        <Button
          testID="settings-restart-checkout"
          title="Choose a plan"
          onPress={openPlanPicker}
        />
      )}
    </View>
  );
}

export function SettingsScreen() {
  const router = useRouter();
  const { user, logout } = useAuth();
  const { business, setBusiness } = useBusiness();
  const [appleCalendarSync, setAppleCalendarSync] = useState(false);

  const handleLogout = () => {
    setBusiness(null);
    logout();
    router.replace("/");
  };

  const handleShareCode = async () => {
    if (!business?.code) return;
    await Share.share({
      message: `Find me on My Trade Portal with code ${business.code}`,
    });
  };

  const sections = [
    {
      title: "Certificates",
      subtitle: "EICR, EIC & Minor Works — BS 7671 validated",
      onPress: () => router.push("/(trade)/certificates"),
    },
    {
      title: "Revenue & costs",
      subtitle: "Paid revenue, outstanding, profit",
      onPress: () => router.push("/(trade)/analytics"),
    },
    {
      title: "Invoices",
      subtitle: "Raise, track & mark paid",
      onPress: () => router.push("/(trade)/invoices"),
    },
    // Business profile and Branding share the same underlying edit screen for
    // beta; Team is deferred to post-beta (sole-owner-operator centric).
    {
      title: "Business profile & branding",
      subtitle: business?.name ?? "Name, logo, colour, quote PDF",
      onPress: () => router.push("/(trade)/branding"),
    },
    {
      title: "Follow-up settings",
      subtitle: "Quote & invoice reminders",
      onPress: () => router.push("/(trade)/follow-ups"),
    },
    {
      title: "Integrations",
      subtitle: "Apple Calendar, payments, accounting",
      onPress: () => {},
    },
  ];

  return (
    <Screen>
      <Header title="Settings" onBack={() => router.back()} />

      <ScrollView className="flex-1" contentContainerClassName="gap-4 pb-4">
        <Text variant="body" color="secondary">
          Business profile, branding, pricing, and team.
        </Text>

        <View className="rounded-2xl bg-slate-100 p-4 gap-2">
          <Text variant="body" weight="semibold">
            Signed in as
          </Text>
          <Text variant="body">{user?.fullName ?? "Guest"}</Text>
          <Text variant="caption" color="secondary">
            {user?.email ?? "Not signed in"}
          </Text>
          <Text variant="caption" color="secondary">
            Business: {business?.name ?? "None selected"}
          </Text>
        </View>

        {business?.code ? (
          <View className="rounded-2xl bg-slate-100 p-4 gap-3">
            <Text variant="body" weight="semibold">
              Customer code
            </Text>
            <Text variant="caption" color="secondary">
              Share this 6-digit code with customers so they can find your business in the app.
            </Text>
            <View className="flex-row items-center justify-between rounded-xl bg-white px-4 py-3">
              <Text testID="settings-customer-code" variant="title" weight="bold" style={{ letterSpacing: 4 }}>
                {business.code}
              </Text>
              <Button title="Share" onPress={handleShareCode} />
            </View>
          </View>
        ) : null}

        <SubscriptionCard />

        <View className="rounded-2xl bg-slate-100 p-4 gap-3">
          <Text variant="body" weight="semibold">
            Settings
          </Text>
          {sections.map((section, index) => (
            <Pressable key={section.title} onPress={section.onPress}>
              <View className={`py-3 ${index !== sections.length - 1 ? "border-b border-slate-200" : ""}`}>
                <Text variant="body" weight="semibold">
                  {section.title}
                </Text>
                <Text variant="caption" color="secondary">
                  {section.subtitle}
                </Text>
              </View>
            </Pressable>
          ))}
        </View>

        <Pressable onPress={() => setAppleCalendarSync((v) => !v)}>
          <View className="rounded-2xl bg-slate-100 p-4 gap-3">
            <View className="flex-row items-center justify-between">
              <Text variant="body" weight="semibold">
                Apple Calendar sync
              </Text>
              <View
                className={`w-12 h-7 rounded-full px-0.5 justify-center ${
                  appleCalendarSync ? "bg-blue-600" : "bg-slate-200"
                }`}
              >
                <View
                  className="w-6 h-6 rounded-full bg-white"
                  style={{ transform: [{ translateX: appleCalendarSync ? 20 : 0 }] }}
                />
              </View>
            </View>
            <Text variant="caption" color="secondary">
              Push booked jobs to your Apple Calendar (EventKit integration in Beta).
            </Text>
          </View>
        </Pressable>

        <Button testID="settings-logout" title="Log out" variant="outline" onPress={handleLogout} />
      </ScrollView>
    </Screen>
  );
}

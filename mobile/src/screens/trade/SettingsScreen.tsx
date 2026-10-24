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
import { api, ApiError } from "../../lib/apiClient";
import { openCalendarSubscription } from "../../api/calendar";
import { config } from "../../lib/config";
import { openInAppBrowser } from "../../lib/inAppBrowser";
import { PortalQrSheet } from "../../components/trade/PortalQrSheet";
import { SubscriptionCard } from "../../components/trade/SubscriptionCard";

/**
 * Read-only subscription status (App Store Guideline 3.1.1): plans are bought
 * and managed on the website, so this section only reports state. The website
 * mentions below are plain text on purpose; they must never become links.
 */
function SubscriptionSection() {
  const { data, isLoading } = useSubscription();

  if (isLoading) {
    return null;
  }

  if (!data) {
    return (
      <View className="rounded-2xl bg-slate-100 p-4 gap-2">
        <Text variant="body" weight="semibold">
          Subscription
        </Text>
        <Text variant="caption" color="secondary">
          You don't have an active plan yet. Start a 14-day free trial to unlock everything.
        </Text>
        <Text variant="caption" color="secondary">
          Subscribe at mytradeportal.co.uk — your plan shows up here automatically.
        </Text>
      </View>
    );
  }

  return <SubscriptionCard subscription={data} />;
}

export function SettingsScreen() {
  const router = useRouter();
  const { user, logout } = useAuth();
  const { business, setBusiness } = useBusiness();
  const [calendarLinkLoading, setCalendarLinkLoading] = useState(false);
  const [calendarLinkError, setCalendarLinkError] = useState<string | null>(null);
  const [showQrSheet, setShowQrSheet] = useState(false);

  const handleCalendarSubscription = async () => {
    setCalendarLinkError(null);
    setCalendarLinkLoading(true);
    try {
      await openCalendarSubscription();
    } catch (error) {
      setCalendarLinkError(
        error instanceof ApiError && error.status === 402
          ? "An active subscription is required for calendar sync — subscribe at mytradeportal.co.uk."
          : "Could not load your calendar link. Please try again."
      );
    } finally {
      setCalendarLinkLoading(false);
    }
  };

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
    // beta.
    {
      title: "Business profile & branding",
      subtitle: business?.name ?? "Name, logo, colour, quote PDF",
      onPress: () => router.push("/(trade)/branding"),
    },
    {
      title: "Team",
      subtitle: "Invite users, see pending invites",
      onPress: () => router.push("/(trade)/team"),
    },
    {
      title: "Payment details",
      subtitle: "Bank transfer details shown on invoices",
      onPress: () => router.push("/(trade)/payment-details"),
    },
    {
      title: "Payments",
      subtitle: "Card payments via Stripe, payouts",
      onPress: () => router.push("/(trade)/payments"),
    },
    {
      title: "Follow-up settings",
      subtitle: "Quote & invoice reminders, total rounding",
      onPress: () => router.push("/(trade)/follow-ups"),
    },
    {
      title: "Working hours",
      subtitle: "Working day times & days for scheduling",
      onPress: () => router.push("/(trade)/working-hours"),
    },
    {
      title: "Share your booking page",
      subtitle: "QR code + link for customers",
      onPress: () => setShowQrSheet(true),
    },
    {
      title: "Help & guides",
      subtitle: "Step-by-step guides for every feature",
      onPress: () => void openInAppBrowser(config.helpUrl),
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

        <SubscriptionSection />

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

        <Pressable
          testID="settings-calendar-subscription"
          disabled={calendarLinkLoading}
          onPress={handleCalendarSubscription}
        >
          <View className="rounded-2xl bg-slate-100 p-4 gap-2">
            <Text variant="body" weight="semibold">
              {calendarLinkLoading ? "Loading…" : "Calendar subscription"}
            </Text>
            <Text variant="caption" color="secondary">
              Subscribe from Apple or Google Calendar to see booked jobs in your calendar app.
            </Text>
            {calendarLinkError && (
              <Text variant="caption" color="warning">
                {calendarLinkError}
              </Text>
            )}
          </View>
        </Pressable>

        <Button testID="settings-logout" title="Log out" variant="outline" onPress={handleLogout} />
      </ScrollView>

      <PortalQrSheet visible={showQrSheet} onClose={() => setShowQrSheet(false)} />
    </Screen>
  );
}

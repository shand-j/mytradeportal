import { useRouter } from "expo-router";
import { useState } from "react";
import { Pressable, ScrollView, View } from "react-native";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { useAuth } from "../../contexts/AuthContext";
import { useBusiness } from "../../theme/ThemeProvider";

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

  const sections = [
    {
      title: "Certificates",
      subtitle: "EICR, EIC & Minor Works — voice-enabled",
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
    {
      title: "Business profile",
      subtitle: business?.name ?? "Not set",
      onPress: () => router.push("/(trade)/branding"),
    },
    {
      title: "Follow-up settings",
      subtitle: "Quote & invoice reminders",
      onPress: () => router.push("/(trade)/follow-ups"),
    },
    {
      title: "Branding",
      subtitle: "Logo, colour, quote PDF template",
      onPress: () => router.push("/(trade)/branding"),
    },
    {
      title: "Team",
      subtitle: "Engineers & assignment",
      onPress: () => {},
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
            Demo mode
          </Text>
          <Text variant="caption" color="secondary">
            This build is an offline interactive prototype for marketing and stakeholder demos. No
            data is persisted or sent to a backend.
          </Text>
        </View>

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
                  className={`w-6 h-6 rounded-full bg-white ${appleCalendarSync ? "translate-x-5" : ""}`}
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

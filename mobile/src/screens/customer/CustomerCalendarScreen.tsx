import { Pressable, ScrollView, View } from "react-native";
import { useRouter } from "expo-router";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { IconButton } from "../../components/ui/IconButton";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { useMyAppointments } from "../../api/appointments";
import { useBusiness } from "../../theme/ThemeProvider";

export function CustomerCalendarScreen() {
  const { business } = useBusiness();
  const router = useRouter();
  const { appointments: liveAppointments, isConnected, isLoading } = useMyAppointments();
  const upcoming = liveAppointments.filter((a) => a.status === "confirmed" || a.status === "completed");
  const businessName = business?.name ?? "your electrician";

  const handleMessage = (jobTitle: string) => {
    router.push({
      pathname: "/(customer)/messages",
      params: { quoteRef: `Booking: ${jobTitle}` },
    });
  };

  return (
    <Screen>
      <Header title="Appointments" />

      <ScrollView className="flex-1" contentContainerStyle={{ gap: 16, paddingBottom: 40 }}>
        <Text variant="body" color="secondary">
          Upcoming appointments and bookings with {businessName}.
        </Text>

        {isLoading && (
          <Text variant="caption" color="secondary" align="center">
            Loading your appointments…
          </Text>
        )}

        {!isConnected && !isLoading && (
          <View className="items-center rounded-2xl border border-slate-200 bg-slate-50 p-6">
            <Text variant="body" color="secondary" align="center">
              Not connected
            </Text>
            <Text variant="caption" color="secondary" align="center">
              Check your connection to view appointments.
            </Text>
          </View>
        )}

        {upcoming.map((job) => (
          <View
            key={job.id}
            className="gap-3 rounded-2xl border border-slate-200 bg-white p-4"
          >
            <View className="flex-row items-start justify-between gap-2">
              <View className="flex-1 gap-1">
                <Text variant="body" weight="semibold" numberOfLines={1}>
                  {job.title}
                </Text>
                <Text variant="caption" color="secondary">
                  {job.date} · {job.time}
                </Text>
                <Text variant="caption" color="secondary" numberOfLines={2}>
                  {businessName} · {job.address}
                </Text>
              </View>
              <IconButton
                icon="message"
                size={22}
                color="#0F1E26"
                onPress={() => handleMessage(job.title)}
                accessibilityLabel="Message business"
              />
            </View>

            <View className="flex-row gap-2">
              <Button
                title="Add to Calendar"
                variant="outline"
                size="sm"
                onPress={() => {}}
              />
              <Button
                title="Message"
                size="sm"
                onPress={() => handleMessage(job.title)}
              />
            </View>
          </View>
        ))}

        {isConnected && upcoming.length === 0 && (
          <View className="items-center rounded-2xl border border-slate-200 bg-slate-50 p-6">
            <Text variant="body" color="secondary" align="center">
              No upcoming bookings.
            </Text>
          </View>
        )}
      </ScrollView>
    </Screen>
  );
}

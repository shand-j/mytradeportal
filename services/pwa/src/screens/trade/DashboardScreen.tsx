import { useMemo, useState } from "react";
import { Pressable, ScrollView, View } from "react-native";
import { useRouter } from "expo-router";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { IconButton } from "../../components/ui/IconButton";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { LeadCard } from "../../components/trade/LeadCard";
import { useAuth } from "../../contexts/AuthContext";
import { MOCK_JOBS } from "../../data/mockJobs";
import { MOCK_LEADS } from "../../data/mockLeads";
import { MOCK_QUOTES, getQuoteTotal } from "../../data/mockQuotes";
import { useBusiness } from "../../theme/ThemeProvider";

const URGENCY_ORDER: Record<string, number> = {
  emergency_today: 0,
  today: 1,
  this_week: 2,
  this_month: 3,
  flexible: 4,
  just_researching: 5,
};

const DAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export type DashboardScreenProps = {
  navigation?: {
    navigate: (name: string, params?: Record<string, unknown>) => void;
  };
};

export function DashboardScreen(_props: DashboardScreenProps) {
  const router = useRouter();
  const { user } = useAuth();
  const { business } = useBusiness();
  const [selectedDateIndex, setSelectedDateIndex] = useState(0);

  const today = new Date();
  const nextDays = useMemo(() => {
    const days = [];
    for (let i = 0; i < 7; i++) {
      const d = new Date(today);
      d.setDate(today.getDate() + i);
      days.push(d);
    }
    return days;
  }, [today]);

  const selectedDayLabel = `${DAY_LABELS[nextDays[selectedDateIndex].getDay()]} ${nextDays[selectedDateIndex].getDate()}`;
  const selectedDayJobs = useMemo(
    () => MOCK_JOBS.filter((_, index) => index % 7 === selectedDateIndex),
    [selectedDateIndex]
  );

  const sortedLeads = useMemo(
    () =>
      [...MOCK_LEADS]
        .filter((lead) => lead.status !== "dead")
        .sort((a, b) => (URGENCY_ORDER[a.urgency] ?? 99) - (URGENCY_ORDER[b.urgency] ?? 99)),
    []
  );

  const pendingQuotes = useMemo(
    () => MOCK_QUOTES.filter((q) => q.status === "sent" || q.status === "draft"),
    []
  );

  const totalOutstanding = useMemo(
    () =>
      pendingQuotes.reduce((sum, quote) => {
        const totals = getQuoteTotal(quote);
        return sum + totals.total;
      }, 0),
    [pendingQuotes]
  );

  return (
    <Screen>
      <Header
        title="Dashboard"
        rightAction={
          <IconButton
            testID="dashboard-more"
            icon="more"
            size={24}
            color="#374151"
            onPress={() => router.push("/(trade)/settings")}
            accessibilityLabel="Settings"
          />
        }
      />
      <ScrollView className="flex-1" contentContainerStyle={{ paddingBottom: 24, gap: 16 }}>
        <View className="gap-0.5">
          <Text variant="body" color="secondary">
            {business?.name ?? "Your business"}
          </Text>
          <Text variant="body" weight="semibold">
            Hi {user?.fullName ?? "there"}
          </Text>
        </View>

        <View className="flex-row gap-3">
          <View className="flex-1 gap-1 rounded-2xl bg-blue-100 p-4">
            <Text variant="caption" color="secondary">
              Active leads
            </Text>
            <Text variant="title" weight="bold">
              {sortedLeads.length}
            </Text>
          </View>
          <View className="flex-1 gap-1 rounded-2xl bg-amber-100 p-4">
            <Text variant="caption" color="secondary">
              Outstanding quotes
            </Text>
            <Text variant="title" weight="bold">
              £{totalOutstanding.toFixed(0)}
            </Text>
          </View>
        </View>

        <View className="gap-3">
          <View className="flex-row items-center justify-between">
            <Text variant="body" weight="semibold">
              Top leads
            </Text>
            <View className="flex-row items-center gap-2">
              <Button title="View all" size="sm" variant="ghost" onPress={() => router.push("/(trade)/quotes")} />
              <Button title="+ New lead" size="sm" variant="outline" onPress={() => router.push("/(trade)/manual-lead")} />
            </View>
          </View>
          {sortedLeads.slice(0, 3).map((lead) => (
            <LeadCard key={lead.id} lead={lead} onPress={() => router.push(`/(trade)/lead/${lead.id}`)} />
          ))}
        </View>

        <View className="gap-3">
          <View className="flex-row items-center justify-between">
            <Text variant="body" weight="semibold">
              Calendar · {selectedDayLabel}
            </Text>
            <Button title="View full" size="sm" variant="ghost" onPress={() => router.push("/(trade)/calendar")} />
          </View>
          <View className="flex-row justify-between gap-1.5">
            {nextDays.map((date, index) => (
              <Pressable key={index} className="flex-1" onPress={() => setSelectedDateIndex(index)}>
                <View
                  className={`items-center justify-center gap-1 rounded-xl py-2 ${selectedDateIndex === index ? "bg-blue-100" : "bg-gray-100"}`}
                >
                  <Text variant="caption" color={selectedDateIndex === index ? "text" : "secondary"}>
                    {DAY_LABELS[date.getDay()].slice(0, 1)}
                  </Text>
                  <Text variant="body" weight={selectedDateIndex === index ? "bold" : "normal"}>
                    {date.getDate()}
                  </Text>
                </View>
              </Pressable>
            ))}
          </View>
          {selectedDayJobs.map((job) => (
            <Pressable key={job.id} onPress={() => router.push(`/(trade)/job/${job.id}`)}>
              <View className="flex-row items-center gap-3 rounded-2xl border border-gray-200 bg-white p-4">
                <View className="h-10 w-1 rounded bg-emerald-500" />
                <View className="flex-1">
                  <Text variant="body" weight="semibold">
                    {job.time}
                  </Text>
                  <Text variant="body">{job.title}</Text>
                  <Text variant="caption" color="secondary">
                    {job.customerName} · {job.postcode}
                  </Text>
                </View>
              </View>
            </Pressable>
          ))}
          {selectedDayJobs.length === 0 && (
            <Text variant="caption" color="secondary">
              No bookings on this day.
            </Text>
          )}
        </View>
      </ScrollView>
    </Screen>
  );
}

import { useMemo, useState } from "react";
import { Pressable, ScrollView, View } from "react-native";
import { useRouter } from "expo-router";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { IconButton } from "../../components/ui/IconButton";
import { Icon } from "../../components/ui/Icon";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { LeadCard } from "../../components/trade/LeadCard";
import { useAuth } from "../../contexts/AuthContext";
import { MOCK_JOBS } from "../../data/mockJobs";
import { MOCK_LEADS } from "../../data/mockLeads";
import { MOCK_QUOTES, getQuoteTotal } from "../../data/mockQuotes";
import { useBusiness } from "../../theme/ThemeProvider";
import { useOfflineStore } from "../../stores/offlineStore";
import { useOutstandingQuotes } from "../../api/quotes";
import { useJobsList } from "../../api/jobs";

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
  const isOnline = useOfflineStore((s) => s.isOnline);
  const toggleOnline = useOfflineStore((s) => s.toggleOnline);
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
  // Connected mode: real jobs from the backend; otherwise mock bookings.
  const { jobs: liveJobs, isConnected: jobsConnected } = useJobsList();
  const jobsSource = jobsConnected ? liveJobs : MOCK_JOBS;
  const selectedDayJobs = useMemo(
    () => jobsSource.filter((_, index) => index % 7 === selectedDateIndex),
    [jobsSource, selectedDateIndex]
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

  const mockOutstanding = useMemo(
    () =>
      pendingQuotes.reduce((sum, quote) => {
        const totals = getQuoteTotal(quote);
        return sum + totals.total;
      }, 0),
    [pendingQuotes]
  );

  // Connected mode: real outstanding total from the backend; otherwise the mock.
  const outstanding = useOutstandingQuotes();
  const totalOutstanding = outstanding.isConnected ? outstanding.total : mockOutstanding;

  return (
    <Screen>
      <Header
        title="Dashboard"
        rightAction={
          <View className="flex-row items-center gap-1">
            <IconButton
              testID="offline-toggle"
              icon={isOnline ? "cloud-done" : "cloud-offline"}
              size={22}
              color={isOnline ? "#16A34A" : "#B45309"}
              onPress={toggleOnline}
              accessibilityLabel="Toggle connectivity"
            />
            <IconButton
              testID="dashboard-more"
              icon="more"
              size={24}
              color="#374151"
              onPress={() => router.push("/(trade)/settings")}
              accessibilityLabel="Settings"
            />
          </View>
        }
      />
      <ScrollView className="flex-1" contentContainerStyle={{ paddingBottom: 24, gap: 16 }}>
        <Pressable
          testID="dashboard-new-lead-banner"
          onPress={() => router.push(`/(trade)/lead/${sortedLeads[0]?.id ?? "1"}`)}
        >
          <View className="flex-row items-center gap-3 rounded-2xl border border-blue-200 bg-blue-50 p-4">
            <View className="h-9 w-9 items-center justify-center rounded-full bg-blue-600">
              <Icon name="sparkles" size={18} color="#FFFFFF" />
            </View>
            <View className="flex-1">
              <Text variant="body" weight="semibold">
                New lead · Consumer unit upgrade
              </Text>
              <Text variant="caption" color="secondary">
                SK8 3NJ · from your customer app · tap to review
              </Text>
            </View>
            <Icon name="navigate" size={18} color="#2563EB" />
          </View>
        </Pressable>

        <View className="gap-0.5">
          <Text variant="body" color="secondary">
            {business?.name ?? "Your business"}
          </Text>
          <Text variant="body" weight="semibold">
            Hi {user?.fullName ?? "there"}
          </Text>
        </View>

        <View className="flex-row gap-3">
          <Pressable
            testID="dashboard-voice-quote"
            className="flex-1"
            onPress={() => router.push("/(trade)/voice-quote")}
          >
            <View className="items-center gap-2 rounded-2xl border border-indigo-200 bg-indigo-50 p-4">
              <View className="h-10 w-10 items-center justify-center rounded-full bg-indigo-600">
                <Icon name="mic" size={20} color="#FFFFFF" />
              </View>
              <Text variant="caption" weight="semibold" align="center">
                Dictate a quote
              </Text>
            </View>
          </Pressable>
          <Pressable
            testID="dashboard-new-cert"
            className="flex-1"
            onPress={() => router.push("/(trade)/certificates")}
          >
            <View className="items-center gap-2 rounded-2xl border border-emerald-200 bg-emerald-50 p-4">
              <View className="h-10 w-10 items-center justify-center rounded-full bg-emerald-600">
                <Icon name="shield" size={20} color="#FFFFFF" />
              </View>
              <Text variant="caption" weight="semibold" align="center">
                New EICR
              </Text>
            </View>
          </Pressable>
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
            <View className="flex-row items-center justify-between">
              <Text variant="caption" color="secondary">
                Outstanding quotes
              </Text>
              {outstanding.isConnected && (
                <View className="flex-row items-center gap-1 rounded-full bg-green-100 px-1.5 py-0.5">
                  <View className="h-1.5 w-1.5 rounded-full bg-green-600" />
                  <Text variant="caption" style={{ color: "#15803D", fontSize: 9 }}>
                    LIVE
                  </Text>
                </View>
              )}
            </View>
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
            <Pressable
              key={job.id}
              testID={`dashboard-job-${job.id}`}
              onPress={() => router.push(`/(trade)/job/${job.id}`)}
            >
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

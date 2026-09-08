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
import { NotificationBell } from "../../components/notifications/NotificationBell";
import { useAuth } from "../../contexts/AuthContext";
import { useBusiness } from "../../theme/ThemeProvider";
import { useOfflineStore } from "../../stores/offlineStore";
import { useOutstandingQuotes } from "../../api/quotes";
import { useJobsList } from "../../api/jobs";
import { useLeadsList } from "../../api/quoteRequests";

const URGENCY_ORDER: Record<string, number> = {
  emergency_today: 0,
  today: 1,
  this_week: 2,
  this_month: 3,
  flexible: 4,
  just_researching: 5,
};

const DAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

/**
 * Rough typical job value (£) per lead category, used for the new-leads
 * banner's estimated-value figure. Client-side heuristic, not a quote.
 */
export const CATEGORY_TYPICAL_VALUE: Record<string, number> = {
  consumer_unit: 850,
  ev_charger: 1100,
  eicr: 250,
  full_rewire: 4500,
  rewire: 4500,
  additional_points: 300,
  socket: 300,
  lighting: 400,
  fault_finding: 200,
  fault: 200,
  emergency_callout: 200,
  other: 500,
};

const DEFAULT_TYPICAL_VALUE = 500;

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
  const { jobs, isLoading: jobsLoading } = useJobsList();
  const selectedDayJobs = useMemo(
    () => jobs.filter((_, index) => index % 7 === selectedDateIndex),
    [jobs, selectedDateIndex]
  );

  const { leads, isLoading: leadsLoading } = useLeadsList();

  const sortedLeads = useMemo(
    () =>
      [...leads]
        .filter((lead) => lead.status !== "dead")
        .sort((a, b) => (URGENCY_ORDER[a.urgency] ?? 99) - (URGENCY_ORDER[b.urgency] ?? 99)),
    [leads]
  );

  // Customer-generated leads still waiting for a quote (manual entries and
  // converted leads are already excluded/handled elsewhere).
  const newCustomerLeads = useMemo(
    () => sortedLeads.filter((lead) => lead.status === "new" && lead.source !== "manual"),
    [sortedLeads]
  );
  const newLeadsEstValue = useMemo(
    () =>
      newCustomerLeads.reduce((sum, lead) => {
        const category = lead.structuredData?.category as string | undefined;
        return sum + (CATEGORY_TYPICAL_VALUE[category ?? "other"] ?? DEFAULT_TYPICAL_VALUE);
      }, 0),
    [newCustomerLeads]
  );

  const { total: totalOutstanding, isLoading: outstandingLoading } = useOutstandingQuotes();

  // "Time saved by AI": weekly quote volume × per-quote manual effort vs the
  // ~2 minute AI draft. Only shown once the tenant shared their metrics.
  const quotesPerWeek = business?.quotesPerWeek ?? 0;
  const avgMinutesPerQuote = business?.avgMinutesPerQuote ?? 0;
  const AI_DRAFT_MINUTES = 2;
  const hoursSavedThisWeek =
    quotesPerWeek > 0 && avgMinutesPerQuote > AI_DRAFT_MINUTES
      ? (quotesPerWeek * (avgMinutesPerQuote - AI_DRAFT_MINUTES)) / 60
      : 0;

  return (
    <Screen>
      <Header
        title="Dashboard"
        rightAction={
          <View className="flex-row items-center gap-1">
            <NotificationBell role="trade" />
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
        {newCustomerLeads.length > 0 && (
          <Pressable
            testID="dashboard-new-lead-banner"
            onPress={() => router.push("/(trade)/quotes")}
          >
            <View className="flex-row items-center gap-3 rounded-2xl border border-blue-200 bg-blue-50 p-4">
              <View className="h-9 w-9 items-center justify-center rounded-full bg-blue-600">
                <Icon name="sparkles" size={18} color="#FFFFFF" />
              </View>
              <View className="flex-1">
                <Text variant="body" weight="semibold">
                  {newCustomerLeads.length} new lead{newCustomerLeads.length === 1 ? "" : "s"} · est.
                  value £{Math.round(newLeadsEstValue).toLocaleString("en-GB")}+
                </Text>
                <Text variant="caption" color="secondary">
                  Review and quote
                </Text>
              </View>
              <Icon name="navigate" size={18} color="#2563EB" />
            </View>
          </Pressable>
        )}

        <View className="gap-0.5">
          {business?.name ? (
            <Text variant="body" color="secondary">
              {business.name}
            </Text>
          ) : (
            <View className="h-4 w-40 rounded bg-neutral-200" />
          )}
          {user?.fullName ? (
            <Text variant="body" weight="semibold">
              Hi {user.fullName}
            </Text>
          ) : (
            <View className="mt-1 h-5 w-32 rounded bg-neutral-200" />
          )}
        </View>

        <View className="flex-row gap-3">
          <View className="flex-1 gap-1 rounded-2xl bg-blue-100 p-4">
            <Text variant="caption" color="secondary">
              Active leads
            </Text>
            {leadsLoading ? (
              <View className="mt-1 h-8 w-10 rounded bg-blue-200" />
            ) : (
              <Text variant="title" weight="bold">
                {sortedLeads.length}
              </Text>
            )}
          </View>
          <View className="flex-1 gap-1 rounded-2xl bg-amber-100 p-4">
            <View className="flex-row items-center justify-between">
              <Text variant="caption" color="secondary">
                Outstanding quotes
              </Text>
              {!outstandingLoading && (
                <View className="flex-row items-center gap-1 rounded-full bg-green-100 px-1.5 py-0.5">
                  <View className="h-1.5 w-1.5 rounded-full bg-green-600" />
                  <Text variant="caption" style={{ color: "#15803D", fontSize: 9 }}>
                    LIVE
                  </Text>
                </View>
              )}
            </View>
            {outstandingLoading ? (
              <View className="mt-1 h-8 w-20 rounded bg-amber-200" />
            ) : (
              <Text variant="title" weight="bold">
                £{totalOutstanding.toFixed(0)}
              </Text>
            )}
          </View>
        </View>

        {hoursSavedThisWeek > 0 && (
          <View
            testID="dashboard-time-saved-card"
            className="flex-row items-center gap-3 rounded-2xl border border-emerald-200 bg-emerald-50 p-4"
          >
            <View className="h-9 w-9 items-center justify-center rounded-full bg-emerald-600">
              <Icon name="flash" size={18} color="#FFFFFF" />
            </View>
            <View className="flex-1">
              <Text variant="body" weight="semibold">
                Time saved by AI
              </Text>
              <Text variant="caption" color="secondary">
                ≈ {hoursSavedThisWeek.toFixed(1)} hrs saved this week · {business?.quotesPerWeek} quotes
                × {business?.avgMinutesPerQuote} min manual vs ~2 min AI draft
              </Text>
            </View>
          </View>
        )}

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

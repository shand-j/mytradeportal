import { useMemo, useState } from "react";
import { Pressable, ScrollView, View } from "react-native";
import { useRouter } from "expo-router";
import { colors } from "@mtp/shared-ts";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { IconButton } from "../../components/ui/IconButton";
import { Icon } from "../../components/ui/Icon";
import { LiveBadge } from "../../components/ui/LiveBadge";
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
import { useDashboardKpis } from "../../api/analytics";
import { useInvoicesList } from "../../api/invoices";
import { Lead } from "../../types";

const DAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

/** Day's jobs shown before the list collapses behind a "more" link. */
const MAX_DAY_JOBS = 3;

/** New quote requests surfaced in the "Top new quotes" section. */
const TOP_NEW_QUOTES_COUNT = 2;

/**
 * Rough typical job value (£) per quote category, used for estimated-value
 * figures. Client-side heuristic, not a quote.
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

function leadEstimatedValue(lead: Lead): number {
  const category = lead.structuredData?.category as string | undefined;
  return CATEGORY_TYPICAL_VALUE[category ?? "other"] ?? DEFAULT_TYPICAL_VALUE;
}

/** Intake completeness in [0, 1]: property type, postcode, ≥1 questionnaire answer. */
function intakeCompleteness(lead: Lead): number {
  const sd = lead.structuredData ?? {};
  const questionnaire = sd.questionnaire as Record<string, unknown> | undefined;
  const hasAnswers =
    !!questionnaire &&
    Object.values(questionnaire).some((v) => v !== undefined && v !== null && v !== "");
  let points = 0;
  if (sd.property) points += 1;
  if (lead.postcode) points += 1;
  if (hasAnswers) points += 1;
  return points / 3;
}

/**
 * Readiness-to-fulfil multiplier in [0, 1]:
 * - base 0.5–1.0 scaled by intake completeness (a full intake can be quoted
 *   and booked without chasing the customer);
 * - halved when the AI triage requested a call-back (can't book until called);
 * - zeroed while a safety review is pending (blocked until triaged).
 */
function leadReadiness(lead: Lead): number {
  if (lead.badge === "Flagged") return 0;
  const callbackFactor = lead.requiresCallback ? 0.5 : 1;
  return (0.5 + 0.5 * intakeCompleteness(lead)) * callbackFactor;
}

/**
 * Top-new-quotes ranking score: expected revenue × readiness to fulfil.
 * High-value jobs with a complete intake and no blocking flags rank first.
 */
function leadScore(lead: Lead): number {
  return leadEstimatedValue(lead) * leadReadiness(lead);
}

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
  const visibleDayJobs = selectedDayJobs.slice(0, MAX_DAY_JOBS);
  const hiddenDayJobs = selectedDayJobs.length - visibleDayJobs.length;

  const { leads, isLoading: leadsLoading } = useLeadsList();

  // New quote requests still waiting for a quote (converted/dead are excluded
  // upstream; "new" = customer submitted, not yet quoted).
  const newLeads = useMemo(() => leads.filter((lead) => lead.status === "new"), [leads]);

  // Customer-submitted requests drive the banner (manual entries excluded).
  const newCustomerLeads = useMemo(
    () => newLeads.filter((lead) => lead.source !== "manual"),
    [newLeads]
  );
  const newLeadsEstValue = useMemo(
    () => newCustomerLeads.reduce((sum, lead) => sum + leadEstimatedValue(lead), 0),
    [newCustomerLeads]
  );

  // Best new quotes by value × readiness; ties broken FIFO (oldest waiting first).
  const topNewQuotes = useMemo(
    () =>
      [...newLeads]
        .sort((a, b) => leadScore(b) - leadScore(a) || a.createdAt.localeCompare(b.createdAt))
        .slice(0, TOP_NEW_QUOTES_COUNT),
    [newLeads]
  );

  const { total: totalOutstanding, isLoading: outstandingLoading } = useOutstandingQuotes();

  // Revenue summary — same /analytics/dashboard source as the full report.
  const { kpi, isLoading: kpiLoading } = useDashboardKpis();
  const { invoices, isLoading: invoicesLoading } = useInvoicesList();
  const outstandingInvoices = useMemo(
    () => invoices.filter((i) => i.status === "sent").reduce((sum, i) => sum + i.amount, 0),
    [invoices]
  );

  // Time saved by AI drafting: AI-generated quote count × ~25 min manual
  // drafting time per quote (backend AI_DRAFT_MANUAL_MINUTES assumption).
  const aiTimeSavedHours = kpi?.aiTimeSavedHours ?? 0;
  const aiGeneratedQuotes = kpi?.aiGeneratedQuotes ?? 0;

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
              color={isOnline ? colors.success : colors.warningText}
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
            onPress={() =>
              router.push({ pathname: "/(trade)/quotes", params: { filter: "new", sort: "fifo" } })
            }
          >
            <View className="flex-row items-center gap-3 rounded-2xl border border-primary-200 bg-primary-50 p-4">
              <View className="h-9 w-9 items-center justify-center rounded-full bg-primary">
                <Icon name="sparkles" size={18} color="#FFC107" />
              </View>
              <View className="flex-1">
                <Text variant="body" weight="semibold">
                  {newCustomerLeads.length} new quote request{newCustomerLeads.length === 1 ? "" : "s"}{" "}
                  · est. value £{Math.round(newLeadsEstValue).toLocaleString("en-GB")}+
                </Text>
                <Text variant="caption" color="secondary">
                  Review and quote
                </Text>
              </View>
              <Icon name="navigate" size={18} color="#0F1E26" />
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
          <Pressable
            testID="dashboard-outstanding-quotes-card"
            className="flex-1"
            onPress={() =>
              router.push({ pathname: "/(trade)/quotes", params: { filter: "new", sort: "fifo" } })
            }
          >
            <View className="flex-1 gap-1 rounded-2xl bg-accent-50 p-4">
              <View className="flex-row items-center justify-between">
                <Text variant="caption" color="secondary">
                  Outstanding quotes
                </Text>
                {!outstandingLoading && <LiveBadge compact />}
              </View>
              {outstandingLoading ? (
                <View className="mt-1 h-8 w-20 rounded bg-accent-100" />
              ) : (
                <Text variant="title" weight="bold">
                  £{totalOutstanding.toFixed(0)}
                </Text>
              )}
              <Text variant="caption" color="secondary">
                New requests, oldest first
              </Text>
            </View>
          </Pressable>
          <View testID="dashboard-time-saved-card" className="flex-1">
            <View className="flex-1 gap-1 rounded-2xl bg-primary-50 p-4">
              <View className="flex-row items-center justify-between">
                <Text variant="caption" color="secondary">
                  Hours saved by AI
                </Text>
                <Icon name="flash" size={14} color="#0F1E26" />
              </View>
              {kpiLoading ? (
                <View className="mt-1 h-8 w-14 rounded bg-primary-100" />
              ) : (
                <Text variant="title" weight="bold">
                  ≈{aiTimeSavedHours.toFixed(1)}
                </Text>
              )}
              <Text variant="caption" color="secondary">
                {aiGeneratedQuotes} AI draft{aiGeneratedQuotes === 1 ? "" : "s"} × ~25 min
              </Text>
            </View>
          </View>
        </View>

        <View className="gap-3">
          <View className="flex-row items-center justify-between">
            <Text variant="body" weight="semibold">
              Revenue
            </Text>
            <Button
              title="View report"
              size="sm"
              variant="ghost"
              onPress={() => router.push("/(trade)/analytics")}
            />
          </View>
          <View className="flex-row gap-3">
            <Pressable
              testID="dashboard-paid-this-month-card"
              className="flex-1"
              onPress={() => router.push("/(trade)/analytics")}
            >
              <View className="flex-1 gap-1 rounded-2xl bg-accent-50 p-4">
                <Text variant="caption" color="secondary">
                  Paid this month
                </Text>
                {kpiLoading ? (
                  <View className="mt-1 h-8 w-20 rounded bg-accent-100" />
                ) : (
                  <Text variant="title" weight="bold">
                    £{(kpi?.revenueThisMonth ?? 0).toFixed(0)}
                  </Text>
                )}
                {!!kpi && kpi.revenueChange !== 0 && (
                  <Text variant="caption" color="secondary">
                    {kpi.revenueChange > 0 ? "▲" : "▼"} {Math.abs(kpi.revenueChange).toFixed(0)}% vs
                    last month
                  </Text>
                )}
              </View>
            </Pressable>
            <Pressable
              testID="dashboard-outstanding-invoices-card"
              className="flex-1"
              onPress={() => router.push("/(trade)/invoices")}
            >
              <View className="flex-1 gap-1 rounded-2xl bg-primary-50 p-4">
                <Text variant="caption" color="secondary">
                  Outstanding invoices
                </Text>
                {invoicesLoading ? (
                  <View className="mt-1 h-8 w-20 rounded bg-primary-100" />
                ) : (
                  <Text variant="title" weight="bold">
                    £{outstandingInvoices.toFixed(0)}
                  </Text>
                )}
              </View>
            </Pressable>
          </View>
        </View>

        <View className="gap-3">
          <View className="flex-row items-center justify-between">
            <Text variant="body" weight="semibold">
              Top new quotes
            </Text>
            <Button
              title="View all"
              size="sm"
              variant="ghost"
              onPress={() => router.push("/(trade)/quotes")}
            />
          </View>
          {topNewQuotes.map((lead) => (
            <LeadCard key={lead.id} lead={lead} onPress={() => router.push(`/(trade)/lead/${lead.id}`)} />
          ))}
          {topNewQuotes.length === 0 && !leadsLoading && (
            <Text variant="caption" color="secondary">
              No new quote requests right now.
            </Text>
          )}
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
                  className={`items-center justify-center gap-1 rounded-xl py-2 ${selectedDateIndex === index ? "bg-primary-100" : "bg-gray-100"}`}
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
          {visibleDayJobs.map((job) => (
            <Pressable
              key={job.id}
              testID={`dashboard-job-${job.id}`}
              onPress={() => router.push(`/(trade)/job/${job.id}`)}
            >
              <View className="flex-row items-center gap-3 rounded-2xl border border-gray-200 bg-white p-4">
                <View className="h-10 w-1 rounded bg-accent-500" />
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
          {hiddenDayJobs > 0 && (
            <Pressable onPress={() => router.push("/(trade)/calendar")}>
              <Text variant="caption" color="secondary">
                +{hiddenDayJobs} more — view calendar
              </Text>
            </Pressable>
          )}
          {selectedDayJobs.length === 0 && !jobsLoading && (
            <Text variant="caption" color="secondary">
              No bookings on this day.
            </Text>
          )}
        </View>
      </ScrollView>
    </Screen>
  );
}

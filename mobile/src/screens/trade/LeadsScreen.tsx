import { useMemo, useState } from "react";
import { Pressable, ScrollView, View } from "react-native";
import { useRouter } from "expo-router";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { LeadCard } from "../../components/trade/LeadCard";
import { useLeadsList } from "../../api/quoteRequests";
import { useQuotesList } from "../../api/quotes";
import { Lead, Quote, QuoteStatus } from "../../types";
import { formatMoneyGBP } from "../../lib/format";

type FilterKey = "all" | "new" | "flagged" | "sent" | "accepted";

const FILTERS: { key: FilterKey; label: string }[] = [
  { key: "all", label: "All" },
  { key: "new", label: "New" },
  { key: "flagged", label: "Flagged" },
  { key: "sent", label: "Sent" },
  { key: "accepted", label: "Accepted" },
];

const URGENCY_ORDER: Record<string, number> = {
  emergency_today: 0,
  today: 1,
  this_week: 2,
  this_month: 3,
  flexible: 4,
  just_researching: 5,
};

const STATUS_COLORS: Record<QuoteStatus, string> = {
  draft: "bg-gray-100",
  sent: "bg-blue-100",
  accepted: "bg-emerald-100",
  rejected: "bg-red-100",
  expired: "bg-gray-100",
};

const STATUS_COPY: Record<QuoteStatus, string> = {
  draft: "Draft",
  sent: "Sent",
  accepted: "Accepted",
  rejected: "Rejected",
  expired: "Expired",
};

export type LeadsScreenProps = {
  navigation?: {
    navigate: (name: string, params?: Record<string, unknown>) => void;
  };
  onBack?: () => void;
  initialSelectedLeadId?: string | null;
  /** Pre-applied list filter (e.g. "new" from the dashboard banner CTA). */
  initialFilter?: FilterKey;
};

export function LeadsScreen({ onBack, initialFilter }: LeadsScreenProps) {
  const router = useRouter();
  const [activeFilter, setActiveFilter] = useState<FilterKey>(initialFilter ?? "all");
  const { leads: realLeads, isLoading: leadsLoading } = useLeadsList();
  const { quotes: realQuotes, isLoading: quotesLoading } = useQuotesList();

  const sortedLeads = useMemo(
    () =>
      [...realLeads]
        .filter((lead) => lead.status !== "dead")
        .sort((a, b) => {
          const urgencyDiff = (URGENCY_ORDER[a.urgency] ?? 99) - (URGENCY_ORDER[b.urgency] ?? 99);
          if (urgencyDiff !== 0) return urgencyDiff;
          // Call-backs first within an urgency group.
          return Number(b.requiresCallback ?? false) - Number(a.requiresCallback ?? false);
        }),
    [realLeads]
  );

  const sortedQuotes = useMemo(
    () =>
      [...realQuotes].sort((a, b) => {
        const statusOrder: Record<QuoteStatus, number> = {
          draft: 0,
          sent: 1,
          accepted: 2,
          rejected: 3,
          expired: 4,
        };
        return statusOrder[a.status] - statusOrder[b.status];
      }),
    [realQuotes]
  );

  const filteredLeads = useMemo(() => {
    if (activeFilter === "all") return sortedLeads;
    if (activeFilter === "new") return sortedLeads.filter((l) => l.badge === "New" || l.status === "new");
    if (activeFilter === "flagged") return sortedLeads.filter((l) => l.badge === "Flagged");
    return [];
  }, [activeFilter, sortedLeads]);

  const filteredQuotes = useMemo(() => {
    if (activeFilter === "all") return sortedQuotes;
    if (activeFilter === "sent") return sortedQuotes.filter((q) => q.status === "sent");
    if (activeFilter === "accepted") return sortedQuotes.filter((q) => q.status === "accepted");
    return [];
  }, [activeFilter, sortedQuotes]);

  const items = useMemo(
    () => [
      ...filteredLeads.map((lead) => ({ kind: "lead" as const, data: lead })),
      ...filteredQuotes.map((quote) => ({ kind: "quote" as const, data: quote })),
    ],
    [filteredLeads, filteredQuotes]
  );

  const isLoading = leadsLoading || quotesLoading;

  return (
    <Screen>
      <Header title="Leads" onBack={onBack} />
      <ScrollView className="flex-1" contentContainerStyle={{ paddingBottom: 24, gap: 16 }}>
        <Text variant="body" color="secondary">
          Live leads and quotes from your connected account, sorted by urgency.
        </Text>

        {isLoading && (
          <Text variant="caption" color="secondary" align="center">
            Loading leads…
          </Text>
        )}

        <View className="flex-row flex-wrap gap-2">
          {FILTERS.map((filter) => (
            <Pressable key={filter.key} onPress={() => setActiveFilter(filter.key)}>
              <View
                className={`rounded-full px-3 py-1.5 ${activeFilter === filter.key ? "bg-blue-100" : "bg-gray-100"}`}
              >
                <Text variant="caption" color={activeFilter === filter.key ? "text" : "secondary"}>
                  {filter.label}
                </Text>
              </View>
            </Pressable>
          ))}
        </View>

        {items.map((item) =>
          item.kind === "lead" ? (
            <LeadCard
              key={`lead-${item.data.id}`}
              lead={item.data}
              onPress={() => router.push(`/(trade)/lead/${item.data.id}`)}
            />
          ) : (
            <QuoteCard
              key={`quote-${item.data.id}`}
              quote={item.data}
              onPress={() => router.push(`/(trade)/quote/${item.data.id}`)}
              testID={`quote-card-${item.data.id}`}
            />
          )
        )}

        {items.length === 0 && (
          <View className="gap-3 rounded-2xl bg-gray-100 p-6">
            <Text variant="body" align="center" color="secondary">
              No {activeFilter === "all" ? "" : activeFilter} items yet.
            </Text>
            <Text variant="caption" align="center" color="secondary">
              Share your QR code or link to start receiving leads.
            </Text>
            <Button title="Share QR code" variant="outline" onPress={() => {}} />
          </View>
        )}

        <Button title="+ New lead" variant="outline" onPress={() => router.push("/(trade)/manual-lead")} />
      </ScrollView>
    </Screen>
  );
}

function QuoteCard({ quote, onPress, testID }: { quote: Quote; onPress: () => void; testID?: string }) {
  const totals = useMemo(() => {
    const subtotal = quote.lineItems.reduce((sum, item) => {
      const qty = parseFloat(item.qty) || 0;
      const price = parseFloat(item.unitPrice) || 0;
      return sum + qty * price;
    }, 0);
    const vat = subtotal * quote.vatRate;
    return { subtotal, vat, total: subtotal + vat };
  }, [quote]);

  return (
    <Pressable testID={testID} onPress={onPress}>
      <View className="gap-2 rounded-2xl border border-gray-200 bg-white p-4">
        <View className="flex-row items-center justify-between gap-2">
          <Text variant="body" weight="semibold" numberOfLines={1} style={{ flex: 1 }}>
            {quote.title}
          </Text>
          <View className={`rounded-lg px-2 py-0.5 ${STATUS_COLORS[quote.status]}`}>
            <Text variant="caption" color="secondary">
              {STATUS_COPY[quote.status]}
            </Text>
          </View>
        </View>
        <Text variant="caption" color="secondary">
          {quote.customerName} · {quote.postcode}
        </Text>
        <Text variant="body" weight="semibold">
          {formatMoneyGBP(totals.total)} inc VAT
        </Text>
      </View>
    </Pressable>
  );
}

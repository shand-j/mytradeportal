import { useEffect, useMemo, useState } from "react";
import { Modal, Pressable, ScrollView, Share, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { LiveBadge } from "../../components/ui/LiveBadge";
import { QrCode } from "../../components/ui/QrCode";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { LeadCard } from "../../components/trade/LeadCard";
import { GeneratingQuoteBanner } from "../../components/trade/GeneratingQuoteBanner";
import { SettingsMenuButton } from "../../components/ui/SettingsMenuButton";
import { useQuotesList } from "../../api/quotes";
import { useLeadsList } from "../../api/quoteRequests";
import { fetchCurrentTenant } from "../../api/businesses";
import { useBusiness } from "../../theme/ThemeProvider";
import { Quote, QuoteStatus } from "../../types";

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
  sent: "bg-info-100",
  accepted: "bg-success-100",
  rejected: "bg-danger-100",
  expired: "bg-gray-100",
  invoiced: "bg-success-100",
  cancelled: "bg-gray-100",
};

const STATUS_COPY: Record<QuoteStatus, string> = {
  draft: "Draft",
  sent: "Sent",
  accepted: "Accepted",
  rejected: "Rejected",
  expired: "Expired",
  invoiced: "Invoiced",
  cancelled: "Cancelled",
};

export type QuotesScreenProps = {
  navigation?: {
    navigate: (name: string, params?: Record<string, unknown>) => void;
  };
};

export function QuotesScreen(_props: QuotesScreenProps) {
  const router = useRouter();
  const { business } = useBusiness();
  const [showQrSheet, setShowQrSheet] = useState(false);
  // Trade login already loads the tenant into the business store; the query is
  // the same cache key the settings screens use, so this is usually free.
  const tenantQuery = useQuery({ queryKey: ["current-tenant"], queryFn: fetchCurrentTenant });
  const tenantSlug = tenantQuery.data?.slug ?? business?.slug ?? null;
  const portalUrl = tenantSlug ? `https://${tenantSlug}.mytradeportal.co.uk` : null;

  const sharePortalLink = () => {
    if (!portalUrl) return;
    void Share.share({
      message: `Get a quote from ${tenantQuery.data?.name ?? business?.name ?? "us"}: ${portalUrl}`,
    });
  };
  // Deep links (e.g. dashboard "Outstanding quotes") arrive with ?filter=&sort=
  const params = useLocalSearchParams<{ filter?: string; sort?: string }>();
  const [activeFilter, setActiveFilter] = useState<FilterKey>(() =>
    FILTERS.some((f) => f.key === params.filter) ? (params.filter as FilterKey) : "all"
  );
  useEffect(() => {
    if (FILTERS.some((f) => f.key === params.filter)) {
      setActiveFilter(params.filter as FilterKey);
    }
  }, [params.filter]);
  const fifo = params.sort === "fifo";

  const { quotes: liveQuotes, isLoading: quotesLoading } = useQuotesList();
  const { leads: liveLeads, isLoading: leadsLoading } = useLeadsList();

  const sortedLeads = useMemo(
    () =>
      [...liveLeads]
        .filter((lead) => lead.status !== "dead")
        .sort((a, b) => (URGENCY_ORDER[a.urgency] ?? 99) - (URGENCY_ORDER[b.urgency] ?? 99)),
    [liveLeads]
  );

  const sortedQuotes = useMemo(
    () =>
      [...liveQuotes].sort((a, b) => {
        const statusOrder: Record<QuoteStatus, number> = {
          draft: 0,
          sent: 1,
          accepted: 2,
          rejected: 3,
          expired: 4,
          invoiced: 5,
          cancelled: 6,
        };
        return statusOrder[a.status] - statusOrder[b.status];
      }),
    [liveQuotes]
  );

  const filteredLeads = useMemo(() => {
    if (activeFilter === "all") return sortedLeads;
    if (activeFilter === "new") {
      const newLeads = sortedLeads.filter((l) => l.badge === "New" || l.status === "new");
      // FIFO by submission time when deep-linked with sort=fifo
      return fifo
        ? [...newLeads].sort((a, b) => a.createdAt.localeCompare(b.createdAt))
        : newLeads;
    }
    if (activeFilter === "flagged") return sortedLeads.filter((l) => l.badge === "Flagged");
    return [];
  }, [activeFilter, sortedLeads, fifo]);

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

  const isLoading = quotesLoading || leadsLoading;

  return (
    <Screen>
      <Header
        title="Quotes"
        rightAction={
          <View className="flex-row items-center gap-1">
            {!isLoading && <LiveBadge />}
            <SettingsMenuButton />
          </View>
        }
      />
      <ScrollView className="flex-1" contentContainerStyle={{ paddingBottom: 24, gap: 16 }}>
        <GeneratingQuoteBanner />

        <Text variant="body" color="secondary">
          All quotes in one place, sorted by urgency.
        </Text>

        <View className="flex-row flex-wrap gap-2">
          {FILTERS.map((filter) => (
            <Pressable key={filter.key} onPress={() => setActiveFilter(filter.key)}>
              <View
                testID={`quotes-filter-${filter.key}`}
                className={`rounded-full px-3 py-1.5 ${activeFilter === filter.key ? "bg-primary-100" : "bg-gray-100"}`}
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
            <Button
              testID="share-qr-button"
              title="Share QR code"
              variant="outline"
              onPress={() => setShowQrSheet(true)}
            />
          </View>
        )}

        <Button
          testID="quotes-new-quote"
          title="+ New quote"
          onPress={() => router.push("/(trade)/quote-intake")}
        />
      </ScrollView>

      <Modal
        testID="qr-modal"
        visible={showQrSheet}
        transparent
        animationType="slide"
        onRequestClose={() => setShowQrSheet(false)}
      >
        <Pressable
          className="flex-1 justify-end bg-black/40"
          onPress={() => setShowQrSheet(false)}
        >
          <Pressable className="rounded-t-3xl bg-white px-6 pt-6 pb-10 gap-4" onPress={() => {}}>
            <Text variant="title" weight="bold" align="center">
              Your customer portal
            </Text>
            <Text variant="caption" color="secondary" align="center">
              Customers scan this to request a quote — print it for your van, invoices, or business cards.
            </Text>
            {portalUrl ? (
              <View className="items-center py-2">
                <QrCode testID="portal-qr-code" value={portalUrl} size={200} />
              </View>
            ) : (
              <Text variant="body" color="secondary" align="center">
                Your portal link is still loading — pull to retry in a moment.
              </Text>
            )}
            {portalUrl && (
              <Text testID="portal-url" variant="body" weight="semibold" align="center">
                {portalUrl}
              </Text>
            )}
            <Button
              testID="qr-share-link"
              title="Share link"
              disabled={!portalUrl}
              onPress={sharePortalLink}
            />
            <Button title="Close" variant="outline" onPress={() => setShowQrSheet(false)} />
          </Pressable>
        </Pressable>
      </Modal>
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
          £{totals.total.toFixed(2)} inc VAT
        </Text>
      </View>
    </Pressable>
  );
}

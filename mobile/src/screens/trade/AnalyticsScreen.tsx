import { useMemo } from "react";
import { ScrollView, StyleSheet, View } from "react-native";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { useDashboardKpis } from "../../api/analytics";
import { useInvoicesList } from "../../api/invoices";

export type AnalyticsScreenProps = {
  onBack: () => void;
};

export function AnalyticsScreen({ onBack }: AnalyticsScreenProps) {
  const { kpi, isLoading: kpiLoading } = useDashboardKpis();
  const { invoices: liveInvoices, isLoading: invoicesLoading } = useInvoicesList();

  const revenue = kpi?.revenueThisMonth ?? 0;
  const outstanding = useMemo(
    () => liveInvoices.filter((i) => i.status === "sent").reduce((sum, i) => sum + i.amount, 0),
    [liveInvoices]
  );
  const quoted = kpi?.pendingQuotesValue ?? 0;
  const costs = 0; // Costs are not yet available from the backend.
  const profit = revenue - costs;

  return (
    <Screen>
      <Header
        title="Revenue & costs"
        onBack={onBack}
        rightAction={
          !(kpiLoading || invoicesLoading) ? (
            <View className="flex-row items-center gap-1 rounded-full bg-green-100 px-2 py-0.5">
              <View className="h-1.5 w-1.5 rounded-full bg-green-600" />
              <Text variant="caption" style={{ color: "#15803D", fontSize: 9 }}>
                LIVE
              </Text>
            </View>
          ) : undefined
        }
      />

      <ScrollView style={styles.scroll} contentContainerStyle={styles.scrollContent}>
        <View style={styles.grid}>
          <View style={[styles.summaryCard, { backgroundColor: "#D1FAE5" }]}>
            <Text variant="caption" color="secondary">
              Paid revenue
            </Text>
            <Text variant="title" weight="bold">
              £{revenue.toFixed(0)}
            </Text>
          </View>
          <View style={[styles.summaryCard, { backgroundColor: "#FEF3C7" }]}>
            <Text variant="caption" color="secondary">
              Outstanding
            </Text>
            <Text variant="title" weight="bold">
              £{outstanding.toFixed(0)}
            </Text>
          </View>
          <View style={[styles.summaryCard, { backgroundColor: "#DBEAFE" }]}>
            <Text variant="caption" color="secondary">
              Quoted
            </Text>
            <Text variant="title" weight="bold">
              £{quoted.toFixed(0)}
            </Text>
          </View>
          <View style={[styles.summaryCard, { backgroundColor: "#FEE2E2" }]}>
            <Text variant="caption" color="secondary">
              Costs
            </Text>
            <Text variant="title" weight="bold">
              £{costs.toFixed(0)}
            </Text>
          </View>
        </View>

        <View style={[styles.card, { backgroundColor: profit >= 0 ? "#ECFDF5" : "#FEF2F2" }]}>
          <Text variant="body" weight="semibold">
            Estimated profit
          </Text>
          <Text variant="title" weight="bold" style={{ color: profit >= 0 ? "#059669" : "#DC2626" }}>
            £{profit.toFixed(0)}
          </Text>
        </View>

      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  scroll: {
    flex: 1,
  },
  scrollContent: {
    flexGrow: 1,
    gap: 16,
    paddingBottom: 24,
  },
  grid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 12,
  },
  summaryCard: {
    width: "47%",
    padding: 16,
    borderRadius: 16,
    gap: 4,
  },
  card: {
    padding: 16,
    borderRadius: 16,
    backgroundColor: "#F3F4F6",
    gap: 8,
  },
  jobRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 8,
  },
});

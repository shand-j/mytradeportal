import { useMemo } from "react";
import { ScrollView, StyleSheet, View } from "react-native";
import { colors } from "@mtp/shared-ts";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { LiveBadge } from "../../components/ui/LiveBadge";
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
        rightAction={!(kpiLoading || invoicesLoading) ? <LiveBadge /> : undefined}
      />

      <ScrollView style={styles.scroll} contentContainerStyle={styles.scrollContent}>
        <View style={styles.grid}>
          <View style={[styles.summaryCard, { backgroundColor: colors.accentSurface }]}>
            <Text variant="caption" color="secondary">
              Paid revenue
            </Text>
            <Text variant="title" weight="bold">
              £{revenue.toFixed(0)}
            </Text>
          </View>
          <View style={[styles.summaryCard, { backgroundColor: colors.infoSurface }]}>
            <Text variant="caption" color="secondary">
              Outstanding
            </Text>
            <Text variant="title" weight="bold" style={{ color: colors.warningText }}>
              £{outstanding.toFixed(0)}
            </Text>
          </View>
          <View style={[styles.summaryCard, { backgroundColor: colors.infoSurface }]}>
            <Text variant="caption" color="secondary">
              Quoted
            </Text>
            <Text variant="title" weight="bold">
              £{quoted.toFixed(0)}
            </Text>
          </View>
          <View style={[styles.summaryCard, { backgroundColor: colors.infoSurface }]}>
            <Text variant="caption" color="secondary">
              Costs
            </Text>
            <Text variant="title" weight="bold" style={{ color: colors.errorText }}>
              £{costs.toFixed(0)}
            </Text>
          </View>
        </View>

        <View style={styles.card}>
          <Text variant="body" weight="semibold">
            Estimated profit
          </Text>
          <Text
            variant="title"
            weight="bold"
            style={{ color: profit >= 0 ? colors.successText : colors.errorText }}
          >
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
    backgroundColor: colors.infoSurface,
    gap: 8,
  },
  jobRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 8,
  },
});

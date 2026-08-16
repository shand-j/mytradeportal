import { useMemo } from "react";
import { ScrollView, StyleSheet, View } from "react-native";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { MOCK_INVOICES } from "../../data/mockInvoices";
import { MOCK_JOBS } from "../../data/mockJobs";
import { MOCK_QUOTES, getQuoteTotal } from "../../data/mockQuotes";

export type AnalyticsScreenProps = {
  onBack: () => void;
};

export function AnalyticsScreen({ onBack }: AnalyticsScreenProps) {
  const revenue = useMemo(
    () => MOCK_INVOICES.filter((i) => i.status === "paid").reduce((sum, i) => sum + i.amount, 0),
    []
  );
  const outstanding = useMemo(
    () => MOCK_INVOICES.filter((i) => i.status === "sent").reduce((sum, i) => sum + i.amount, 0),
    []
  );
  const quoted = useMemo(
    () => MOCK_QUOTES.filter((q) => q.status === "sent").reduce((sum, q) => sum + getQuoteTotal(q).total, 0),
    []
  );
  const costs = useMemo(
    () => MOCK_JOBS.reduce((sum, j) => sum + (j.materialCost ?? 0) + (j.labourCost ?? 0), 0),
    []
  );
  const profit = revenue - costs;

  return (
    <Screen>
      <Header title="Revenue & costs" onBack={onBack} />

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

        <View style={styles.card}>
          <Text variant="body" weight="semibold">
            Recent jobs
          </Text>
          {MOCK_JOBS.slice(0, 5).map((job) => (
            <View key={job.id} style={styles.jobRow}>
              <Text variant="body" style={{ flex: 1 }} numberOfLines={1}>
                {job.title}
              </Text>
              <Text variant="caption" color="secondary">
                £{((job.materialCost ?? 0) + (job.labourCost ?? 0)).toFixed(0)}
              </Text>
            </View>
          ))}
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

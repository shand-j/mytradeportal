import { useMemo } from "react";
import { Pressable, ScrollView, StyleSheet, View } from "react-native";
import { useRouter } from "expo-router";
import { Header } from "../../components/ui/Header";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { useInvoicesList } from "../../api/invoices";

export type InvoicesScreenProps = {
  onBack: () => void;
};

export function InvoicesScreen({ onBack }: InvoicesScreenProps) {
  const router = useRouter();
  const { invoices, isLoading } = useInvoicesList();

  const totals = useMemo(() => {
    const outstanding = invoices
      .filter((i) => i.status === "sent")
      .reduce((sum, i) => sum + i.amount, 0);
    const paid = invoices
      .filter((i) => i.status === "paid")
      .reduce((sum, i) => sum + i.amount, 0);
    return { outstanding, paid, total: outstanding + paid };
  }, [invoices]);

  return (
    <Screen>
      <Header
        title="Invoices"
        onBack={onBack}
        rightAction={
          !isLoading ? (
            <View className="flex-row items-center gap-1 rounded-full bg-green-100 px-2 py-0.5">
              <View className="h-1.5 w-1.5 rounded-full bg-green-600" />
              <Text variant="caption" style={{ color: "#15803D", fontSize: 9 }}>
                LIVE
              </Text>
            </View>
          ) : undefined
        }
      />

      <View style={styles.summaryRow}>
        <View style={[styles.summaryCard, { backgroundColor: "#FEF3C7" }]}>
          <Text variant="caption" color="secondary">
            Outstanding
          </Text>
          <Text variant="title" weight="bold">
            £{totals.outstanding.toFixed(0)}
          </Text>
        </View>
        <View style={[styles.summaryCard, { backgroundColor: "#D1FAE5" }]}>
          <Text variant="caption" color="secondary">
            Paid
          </Text>
          <Text variant="title" weight="bold">
            £{totals.paid.toFixed(0)}
          </Text>
        </View>
      </View>

      <ScrollView style={styles.scroll} contentContainerStyle={styles.scrollContent}>
        {invoices.map((invoice) => (
          <Pressable
            key={invoice.id}
            testID={`invoice-card-${invoice.id}`}
            onPress={() => router.push(`/(trade)/invoice/${invoice.id}`)}
          >
            <View style={styles.card}>
              <View style={styles.row}>
                <Text variant="body" weight="semibold" style={{ flex: 1 }} numberOfLines={1}>
                  {invoice.title}
                </Text>
                <View style={[styles.badge, invoice.status === "paid" && styles.paidBadge]}>
                  <Text variant="caption" color="secondary">
                    {invoice.status.toUpperCase()}
                  </Text>
                </View>
              </View>
              <Text variant="caption" color="secondary">
                {invoice.customerName}
              </Text>
              <Text variant="body" weight="semibold">
                £{invoice.amount.toFixed(2)}
              </Text>
              <Text variant="caption" color="secondary">
                {invoice.status === "paid"
                  ? `Paid ${new Date(invoice.paidAt ?? invoice.dueDate).toLocaleDateString()}`
                  : `Due ${new Date(invoice.dueDate).toLocaleDateString()}`}
              </Text>
            </View>
          </Pressable>
        ))}
        {invoices.length === 0 && (
          <View style={styles.card}>
            <Text variant="body" color="secondary" align="center">
              No invoices yet. Complete a job to raise one.
            </Text>
          </View>
        )}
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  summaryRow: {
    flexDirection: "row",
    gap: 12,
    marginBottom: 16,
  },
  summaryCard: {
    flex: 1,
    padding: 16,
    borderRadius: 16,
    gap: 4,
  },
  scroll: {
    flex: 1,
  },
  scrollContent: {
    flexGrow: 1,
    gap: 12,
    paddingBottom: 24,
  },
  card: {
    padding: 16,
    borderRadius: 16,
    backgroundColor: "#FFFFFF",
    borderWidth: 1,
    borderColor: "#E5E7EB",
    gap: 8,
  },
  row: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 8,
  },
  badge: {
    backgroundColor: "#FEF3C7",
    borderRadius: 8,
    paddingHorizontal: 8,
    paddingVertical: 2,
  },
  paidBadge: {
    backgroundColor: "#D1FAE5",
  },
});

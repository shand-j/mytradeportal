import { useMemo, useState } from "react";
import { ScrollView, StyleSheet, View } from "react-native";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { MOCK_INVOICES } from "../../data/mockInvoices";

export type InvoicesScreenProps = {
  onBack: () => void;
};

export function InvoicesScreen({ onBack }: InvoicesScreenProps) {
  const [invoices, setInvoices] = useState(MOCK_INVOICES);

  const totals = useMemo(() => {
    const outstanding = invoices
      .filter((i) => i.status === "sent")
      .reduce((sum, i) => sum + i.amount, 0);
    const paid = invoices
      .filter((i) => i.status === "paid")
      .reduce((sum, i) => sum + i.amount, 0);
    return { outstanding, paid, total: outstanding + paid };
  }, [invoices]);

  const markPaid = (id: string) => {
    setInvoices((prev) =>
      prev.map((i) => (i.id === id ? { ...i, status: "paid", paidAt: new Date().toISOString() } : i))
    );
  };

  const sendReminder = (id: string) => {
    // eslint-disable-next-line no-console
    console.log("Send reminder for invoice", id);
  };

  return (
    <Screen>
      <Header title="Invoices" onBack={onBack} />

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
          <View key={invoice.id} style={styles.card}>
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
            {invoice.status === "sent" && (
              <View style={styles.actions}>
                <Button title="Mark paid" size="sm" onPress={() => markPaid(invoice.id)} />
                <Button title="Send reminder" size="sm" variant="outline" onPress={() => sendReminder(invoice.id)} />
              </View>
            )}
          </View>
        ))}
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
  actions: {
    flexDirection: "row",
    gap: 8,
    marginTop: 4,
  },
});

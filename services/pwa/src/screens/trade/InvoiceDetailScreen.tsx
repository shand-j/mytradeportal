import { ScrollView, StyleSheet, View } from "react-native";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { Invoice } from "../../types";

export type InvoiceDetailScreenProps = {
  invoice: Invoice;
  onClose: () => void;
};

export function InvoiceDetailScreen({ invoice, onClose }: InvoiceDetailScreenProps) {
  const isPaid = invoice.status === "paid";
  const isSent = invoice.status === "sent";
  const isOverdue = invoice.status === "overdue";

  return (
    <Screen>
      <Header title="Invoice" onBack={onClose} />

      <ScrollView style={styles.scroll} contentContainerStyle={styles.scrollContent}>
        <View style={[styles.card, styles.totalCard]}>
          <Text variant="caption" color="secondary">
            {invoice.title}
          </Text>
          <Text variant="title" weight="bold">
            £{invoice.amount.toFixed(2)}
          </Text>
          <View style={[styles.badge, { backgroundColor: statusColor(invoice.status) }]}>
            <Text variant="caption" color="secondary">
              {invoice.status.toUpperCase()}
            </Text>
          </View>
        </View>

        <View style={styles.card}>
          <Text variant="body" weight="semibold">
            Customer
          </Text>
          <Text variant="body">{invoice.customerName}</Text>
        </View>

        <View style={styles.card}>
          <Text variant="body" weight="semibold">
            Dates
          </Text>
          <Text variant="body" color="secondary">
            Sent {invoice.sentAt ? new Date(invoice.sentAt).toLocaleDateString() : "—"}
          </Text>
          <Text variant="body" color="secondary">
            Due {new Date(invoice.dueDate).toLocaleDateString()}
          </Text>
          {invoice.paidAt && (
            <Text variant="body" color="secondary">
              Paid {new Date(invoice.paidAt).toLocaleDateString()}
            </Text>
          )}
        </View>

        <View style={styles.card}>
          <Text variant="body" weight="semibold">
            Payment method
          </Text>
          <Text variant="body" color="secondary">
            Bank transfer · Sort code 20-00-00 · Acc 12345678
          </Text>
        </View>
      </ScrollView>

      <View style={styles.footer}>
        {isPaid && <Button title="Send receipt" variant="outline" onPress={onClose} />}
        {isSent && (
          <>
            <Button title="Mark as paid" onPress={onClose} />
            <Button title="Send reminder" variant="outline" onPress={onClose} />
          </>
        )}
        {(isOverdue || invoice.status === "draft") && (
          <>
            <Button title="Send invoice" onPress={onClose} />
            <Button title="Edit invoice" variant="outline" onPress={onClose} />
          </>
        )}
      </View>
    </Screen>
  );
}

function statusColor(status: Invoice["status"]): string {
  switch (status) {
    case "paid":
      return "#D1FAE5";
    case "sent":
      return "#DBEAFE";
    case "overdue":
      return "#FEE2E2";
    default:
      return "#FEF3C7";
  }
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
  card: {
    padding: 16,
    borderRadius: 16,
    backgroundColor: "#F3F4F6",
    gap: 8,
  },
  totalCard: {
    alignItems: "center",
    paddingVertical: 24,
    backgroundColor: "#EFF6FF",
  },
  badge: {
    borderRadius: 8,
    paddingHorizontal: 8,
    paddingVertical: 2,
    marginTop: 8,
  },
  footer: {
    gap: 12,
    paddingVertical: 16,
    borderTopWidth: 1,
    borderTopColor: "#E5E7EB",
  },
});

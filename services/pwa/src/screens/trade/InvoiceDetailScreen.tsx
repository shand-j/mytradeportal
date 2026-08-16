import { useState } from "react";
import { ScrollView, StyleSheet, View } from "react-native";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { Icon } from "../../components/ui/Icon";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { MOCK_INVOICES } from "../../data/mockInvoices";
import { Invoice, InvoiceStatus } from "../../types";

export type InvoiceDetailScreenProps = {
  invoice: Invoice;
  onClose: () => void;
  onViewRevenue?: () => void;
};

export function InvoiceDetailScreen({ invoice, onClose, onViewRevenue }: InvoiceDetailScreenProps) {
  const [status, setStatus] = useState<InvoiceStatus>(invoice.status);
  const [paidAt, setPaidAt] = useState<string | undefined>(invoice.paidAt);

  const isPaid = status === "paid";
  const isSent = status === "sent";
  const isOverdue = status === "overdue";

  const markPaid = () => {
    const now = new Date().toISOString();
    setStatus("paid");
    setPaidAt(now);
    // Reflect the payment in the shared mock so the revenue dashboard updates.
    const record = MOCK_INVOICES.find((i) => i.id === invoice.id);
    if (record) {
      record.status = "paid";
      record.paidAt = now;
    }
  };

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
          <View style={[styles.badge, { backgroundColor: statusColor(status) }]}>
            <Text variant="caption" color="secondary">
              {status.toUpperCase()}
            </Text>
          </View>
        </View>

        {isPaid && (
          <View style={styles.paidBanner} testID="invoice-paid-banner">
            <View style={styles.paidIcon}>
              <Icon name="checkmark" size={22} color="#FFFFFF" />
            </View>
            <View style={{ flex: 1 }}>
              <Text variant="body" weight="semibold" style={{ color: "#065F46" }}>
                Payment received
              </Text>
              <Text variant="caption" color="secondary">
                £{invoice.amount.toFixed(2)} paid by {invoice.customerName}
              </Text>
            </View>
          </View>
        )}

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
          {paidAt && (
            <Text variant="body" color="secondary">
              Paid {new Date(paidAt).toLocaleDateString()}
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
        {isPaid && (
          <>
            <Button
              testID="invoice-view-revenue"
              title="View revenue dashboard"
              onPress={() => onViewRevenue?.()}
            />
            <Button title="Send receipt" variant="outline" onPress={onClose} />
          </>
        )}
        {isSent && (
          <>
            <Button testID="invoice-mark-paid" title="Mark as paid" onPress={markPaid} />
            <Button title="Send reminder" variant="outline" onPress={onClose} />
          </>
        )}
        {(isOverdue || status === "draft") && (
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
  paidBanner: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    padding: 16,
    borderRadius: 16,
    backgroundColor: "#ECFDF5",
    borderWidth: 1,
    borderColor: "#A7F3D0",
  },
  paidIcon: {
    height: 40,
    width: 40,
    borderRadius: 20,
    backgroundColor: "#10B981",
    alignItems: "center",
    justifyContent: "center",
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

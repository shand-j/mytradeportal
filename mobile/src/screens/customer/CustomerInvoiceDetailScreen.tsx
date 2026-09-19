import { useState } from "react";
import { Linking, ScrollView, StyleSheet, View } from "react-native";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { Icon } from "../../components/ui/Icon";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { CustomerInvoice, usePayMyInvoice } from "../../api/customerInvoices";
import { ApiError } from "../../lib/apiClient";
import { formatDateUK, formatMoneyGBP } from "../../lib/format";

const STATUS_STYLES: Record<string, { background: string; label: string }> = {
  sent: { background: "#E2E8EB", label: "AWAITING PAYMENT" },
  overdue: { background: "#FEF2F2", label: "OVERDUE" },
  paid: { background: "#ECFDF5", label: "PAID" },
};

function errorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.detail;
  if (err instanceof Error) return err.message;
  return fallback;
}

export type CustomerInvoiceDetailScreenProps = {
  invoice: CustomerInvoice;
  onBack: () => void;
};

export function CustomerInvoiceDetailScreen({ invoice, onBack }: CustomerInvoiceDetailScreenProps) {
  const pay = usePayMyInvoice();
  const [payError, setPayError] = useState<string | null>(null);

  const isPaid = invoice.status === "paid";
  const statusStyle = STATUS_STYLES[invoice.status] ?? STATUS_STYLES.sent;
  const vatPercent = Math.round((parseFloat(invoice.vatRate) || 0) * 100);

  const handlePay = async () => {
    setPayError(null);
    try {
      const payLink = await pay.mutateAsync(invoice.id);
      await Linking.openURL(payLink.paymentUrl);
    } catch (err) {
      setPayError(errorMessage(err, "Couldn't start the payment. Please try again."));
    }
  };

  return (
    <Screen>
      <Header title="Invoice" onBack={onBack} />

      <ScrollView style={styles.scroll} contentContainerStyle={styles.scrollContent}>
        <View style={[styles.card, styles.totalCard]}>
          <Text variant="caption" color="secondary">
            {invoice.businessName} · {invoice.invoiceNumber}
          </Text>
          <Text variant="title" weight="bold" testID="invoice-total">
            {formatMoneyGBP(parseFloat(invoice.total) || 0)}
          </Text>
          <View style={[styles.badge, { backgroundColor: statusStyle.background }]}>
            <Text variant="caption" color="secondary">
              {statusStyle.label}
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
                Paid {formatDateUK(invoice.paidAt)}
              </Text>
            </View>
          </View>
        )}

        <View style={styles.card}>
          <Text variant="body" weight="semibold">
            Line items
          </Text>
          {invoice.lineItems.map((item) => (
            <View key={item.id} style={styles.lineRow}>
              <View style={{ flex: 1 }}>
                <Text variant="body">{item.description}</Text>
                <Text variant="caption" color="secondary">
                  {parseFloat(item.quantity) || 0} ×{" "}
                  {formatMoneyGBP(parseFloat(item.unitPrice) || 0)}
                </Text>
              </View>
              <Text variant="body">{formatMoneyGBP(parseFloat(item.total) || 0)}</Text>
            </View>
          ))}
          {invoice.lineItems.length === 0 && (
            <Text variant="caption" color="secondary">
              No line items on this invoice.
            </Text>
          )}
        </View>

        <View style={styles.card}>
          <Text variant="body" weight="semibold">
            Totals
          </Text>
          <View style={styles.lineRow}>
            <Text variant="body" color="secondary" style={{ flex: 1 }}>
              Subtotal
            </Text>
            <Text variant="body">{formatMoneyGBP(parseFloat(invoice.subtotal) || 0)}</Text>
          </View>
          <View style={styles.lineRow}>
            <Text variant="body" color="secondary" style={{ flex: 1 }}>
              VAT ({vatPercent}%)
            </Text>
            <Text variant="body">{formatMoneyGBP(parseFloat(invoice.vatAmount) || 0)}</Text>
          </View>
          <View style={styles.lineRow}>
            <Text variant="body" weight="semibold" style={{ flex: 1 }}>
              Total
            </Text>
            <Text variant="body" weight="bold">
              {formatMoneyGBP(parseFloat(invoice.total) || 0)}
            </Text>
          </View>
        </View>

        <View style={styles.card}>
          <Text variant="body" weight="semibold">
            Dates
          </Text>
          <Text variant="body" color="secondary">
            Issued {formatDateUK(invoice.issueDate)}
          </Text>
          <Text variant="body" color="secondary">
            Due {formatDateUK(invoice.dueDate)}
          </Text>
          {invoice.paidAt && (
            <Text variant="body" color="secondary">
              Paid {formatDateUK(invoice.paidAt)}
            </Text>
          )}
        </View>
      </ScrollView>

      {!isPaid && invoice.paymentUrl && (
        <View style={styles.footer}>
          {payError && (
            <View className="rounded-2xl bg-amber-50 p-3">
              <Text testID="invoice-pay-error" variant="caption" color="warning">
                {payError}
              </Text>
            </View>
          )}
          <Button
            testID="invoice-pay"
            title={pay.isPending ? "Starting secure checkout…" : "Pay now"}
            disabled={pay.isPending}
            onPress={() => void handlePay()}
          />
          <Text variant="caption" color="secondary" align="center">
            You'll be taken to a secure card checkout to pay {invoice.businessName}.
          </Text>
        </View>
      )}
      {!isPaid && !invoice.paymentUrl && (
        <View style={styles.footer}>
          <Text variant="caption" color="secondary" align="center">
            To pay, use the bank transfer details on your invoice email — or contact{" "}
            {invoice.businessName}.
          </Text>
        </View>
      )}
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
  card: {
    padding: 16,
    borderRadius: 16,
    backgroundColor: "#F3F4F6",
    gap: 8,
  },
  totalCard: {
    alignItems: "center",
    paddingVertical: 24,
    backgroundColor: "#FEF9E8",
  },
  lineRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
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

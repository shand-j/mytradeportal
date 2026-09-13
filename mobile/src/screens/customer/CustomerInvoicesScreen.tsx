import { Pressable, ScrollView, View } from "react-native";
import { useRouter } from "expo-router";
import { Header } from "../../components/ui/Header";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { useMyInvoices } from "../../api/customerInvoices";
import { formatDateUK, formatMoneyGBP } from "../../lib/format";
import { useBusiness } from "../../theme/ThemeProvider";

const STATUS_STYLES: Record<string, { background: string; border: string; text: string; label: string }> = {
  sent: { label: "AWAITING PAYMENT", background: "#F2F5F6", border: "#C3CFD5", text: "#0F1E26" },
  overdue: { label: "OVERDUE", background: "#FEF2F2", border: "#FECACA", text: "#B91C1C" },
  paid: { label: "PAID", background: "#ECFDF5", border: "#A7F3D0", text: "#065F46" },
};

function StatusChip({ status }: { status: string }) {
  const style = STATUS_STYLES[status] ?? STATUS_STYLES.sent;
  return (
    <View
      className="rounded-lg border px-2 py-1"
      style={{ backgroundColor: style.background, borderColor: style.border }}
    >
      <Text variant="caption" weight="semibold" style={{ color: style.text, fontSize: 10 }}>
        {style.label}
      </Text>
    </View>
  );
}

export function CustomerInvoicesScreen() {
  const router = useRouter();
  const { business } = useBusiness();
  const { invoices, isConnected, isLoading } = useMyInvoices();
  const businessName = business?.name ?? "your electrician";

  return (
    <Screen>
      <Header title="Invoices" />

      <ScrollView
        testID="invoice-list"
        className="flex-1"
        contentContainerStyle={{ gap: 12, paddingBottom: 40 }}
      >
        <Text variant="body" color="secondary">
          Invoices from {businessName}. Tap one to see the breakdown and pay online.
        </Text>

        {isLoading && (
          <Text variant="caption" color="secondary" align="center">
            Loading your invoices…
          </Text>
        )}

        {!isConnected && !isLoading && (
          <View className="items-center rounded-2xl border border-slate-200 bg-slate-50 p-6">
            <Text variant="body" color="secondary" align="center">
              Not connected
            </Text>
            <Text variant="caption" color="secondary" align="center">
              Check your connection to view invoices.
            </Text>
          </View>
        )}

        {invoices.map((invoice) => (
          <Pressable
            key={invoice.id}
            testID={`invoice-${invoice.id}`}
            onPress={() => router.push(`/(customer)/invoice/${invoice.id}`)}
          >
            <View className="gap-2 rounded-2xl border border-slate-200 bg-white p-4">
              <View className="flex-row items-center justify-between gap-2">
                <Text variant="body" weight="semibold" style={{ flex: 1 }} numberOfLines={1}>
                  {invoice.notes || invoice.invoiceNumber}
                </Text>
                <StatusChip status={invoice.status} />
              </View>
              <Text variant="caption" color="secondary">
                {invoice.businessName} · {invoice.invoiceNumber}
              </Text>
              <Text variant="body" weight="semibold">
                {formatMoneyGBP(parseFloat(invoice.total) || 0)}
              </Text>
              <Text variant="caption" color="secondary">
                {invoice.status === "paid"
                  ? `Paid ${formatDateUK(invoice.paidAt)}`
                  : `Due ${formatDateUK(invoice.dueDate)}`}
              </Text>
            </View>
          </Pressable>
        ))}

        {isConnected && invoices.length === 0 && (
          <View className="items-center rounded-2xl border border-slate-200 bg-slate-50 p-6">
            <Text variant="body" color="secondary" align="center">
              No invoices yet.
            </Text>
            <Text variant="caption" color="secondary" align="center">
              When {businessName} sends you an invoice it will appear here.
            </Text>
          </View>
        )}
      </ScrollView>
    </Screen>
  );
}

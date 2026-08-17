import { useLocalSearchParams, useRouter } from "expo-router";
import { InvoiceDetailScreen } from "../../../src/screens/trade/InvoiceDetailScreen";
import { MOCK_INVOICES } from "../../../src/data/mockInvoices";
import { useInvoice, useMarkInvoicePaid } from "../../../src/api/invoices";

export default function InvoiceDetailRoute() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();

  // Connected mode: resolve the real invoice; otherwise mock.
  const { invoice: realInvoice } = useInvoice(id);
  const markPaid = useMarkInvoicePaid();
  const invoice = realInvoice ?? MOCK_INVOICES.find((i) => i.id === id);

  if (!invoice) return null;

  const isReal = !!realInvoice;

  return (
    <InvoiceDetailScreen
      invoice={invoice}
      onClose={() => router.back()}
      onViewRevenue={() => router.push("/(trade)/analytics")}
      onMarkPaid={isReal ? () => markPaid.mutateAsync(invoice.id).then(() => undefined) : undefined}
      markingPaid={markPaid.isPending}
    />
  );
}

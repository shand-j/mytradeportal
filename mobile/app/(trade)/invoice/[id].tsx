import { useLocalSearchParams, useRouter } from "expo-router";
import { InvoiceDetailScreen } from "../../../src/screens/trade/InvoiceDetailScreen";
import { useInvoice, useMarkInvoicePaid } from "../../../src/api/invoices";

export default function InvoiceDetailRoute() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();

  const { invoice: realInvoice } = useInvoice(id);
  const markPaid = useMarkInvoicePaid();

  if (!realInvoice) return null;

  return (
    <InvoiceDetailScreen
      invoice={realInvoice}
      onClose={() => router.back()}
      onViewRevenue={() => router.push("/(trade)/analytics")}
      onMarkPaid={() => markPaid.mutateAsync(realInvoice.id).then(() => undefined)}
      markingPaid={markPaid.isPending}
    />
  );
}

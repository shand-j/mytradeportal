import { useLocalSearchParams, useRouter } from "expo-router";
import { InvoiceDetailScreen } from "../../../src/screens/trade/InvoiceDetailScreen";
import { MOCK_INVOICES } from "../../../src/data/mockInvoices";

export default function InvoiceDetailRoute() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const invoice = MOCK_INVOICES.find((i) => i.id === id);

  if (!invoice) return null;

  return <InvoiceDetailScreen invoice={invoice} onClose={() => router.back()} />;
}

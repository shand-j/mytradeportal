import { useLocalSearchParams, useRouter } from "expo-router";
import { InvoiceDetailScreen } from "../../../src/screens/trade/InvoiceDetailScreen";
import {
  UpdateInvoiceInput,
  useInvoice,
  useMarkInvoicePaid,
  useSendInvoice,
  useUpdateInvoice,
} from "../../../src/api/invoices";

export default function InvoiceDetailRoute() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();

  const { invoice: realInvoice, apiInvoice } = useInvoice(id);
  const markPaid = useMarkInvoicePaid();
  const sendInvoice = useSendInvoice();
  const updateInvoice = useUpdateInvoice();

  if (!realInvoice) return null;

  const subtotal = apiInvoice ? parseFloat(apiInvoice.subtotal) : 0;
  const vatRate =
    apiInvoice && subtotal > 0 ? parseFloat(apiInvoice.vatAmount) / subtotal : 0.2;

  return (
    <InvoiceDetailScreen
      invoice={realInvoice}
      onClose={() => router.back()}
      onViewRevenue={() => router.push("/(trade)/analytics")}
      onMarkPaid={() => markPaid.mutateAsync(realInvoice.id).then(() => undefined)}
      markingPaid={markPaid.isPending}
      onSendInvoice={() => sendInvoice.mutateAsync(realInvoice.id).then(() => undefined)}
      sendingInvoice={sendInvoice.isPending}
      lineItems={apiInvoice?.lineItems ?? []}
      vatRate={vatRate}
      onSaveLineItems={(lineItems: NonNullable<UpdateInvoiceInput["lineItems"]>) =>
        updateInvoice.mutateAsync({ id: realInvoice.id, input: { lineItems } })
      }
      savingLineItems={updateInvoice.isPending}
    />
  );
}

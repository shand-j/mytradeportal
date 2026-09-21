import { useLocalSearchParams, useRouter } from "expo-router";
import { InvoiceDetailScreen } from "../../../src/screens/trade/InvoiceDetailScreen";
import {
  UpdateInvoiceInput,
  useInvoice,
  useMarkInvoicePaid,
  useRefundInvoice,
  useSendInvoice,
  useSendInvoiceSms,
  useUpdateInvoice,
} from "../../../src/api/invoices";
import { usePaymentsStatus } from "../../../src/api/payments";

export default function InvoiceDetailRoute() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();

  const { invoice: realInvoice, apiInvoice } = useInvoice(id);
  const markPaid = useMarkInvoicePaid();
  const sendInvoice = useSendInvoice();
  const sendInvoiceSms = useSendInvoiceSms();
  const updateInvoice = useUpdateInvoice();
  const refundInvoice = useRefundInvoice();
  const paymentsStatus = usePaymentsStatus();

  if (!realInvoice) return null;

  // The per-invoice card-payments override only renders when Stripe is
  // connected and able to take card payments — otherwise it can never work.
  const stripeEnabled = Boolean(
    paymentsStatus.data?.connected && paymentsStatus.data?.chargesEnabled
  );

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
      onSendInvoiceSms={() => sendInvoiceSms.mutateAsync(realInvoice.id).then(() => undefined)}
      sendingSms={sendInvoiceSms.isPending}
      smsAvailable={apiInvoice?.smsAvailable ?? false}
      lineItems={apiInvoice?.lineItems ?? []}
      vatRate={vatRate}
      roundingAdjustment={parseFloat(apiInvoice?.roundingAdjustment ?? "") || 0}
      onSaveLineItems={(lineItems: NonNullable<UpdateInvoiceInput["lineItems"]>) =>
        updateInvoice.mutateAsync({ id: realInvoice.id, input: { lineItems } })
      }
      savingLineItems={updateInvoice.isPending}
      paidVia={apiInvoice?.paidVia ?? null}
      acceptCardPayments={apiInvoice?.acceptCardPayments ?? null}
      stripeEnabled={stripeEnabled}
      onSetCardPayments={(value: boolean | null) =>
        updateInvoice
          .mutateAsync({ id: realInvoice.id, input: { acceptCardPayments: value } })
          .then(() => undefined)
      }
      savingCardPayments={updateInvoice.isPending}
      onRefund={() => refundInvoice.mutateAsync(realInvoice.id).then(() => undefined)}
      refunding={refundInvoice.isPending}
    />
  );
}

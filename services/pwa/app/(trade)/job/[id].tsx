import { useLocalSearchParams, useRouter } from "expo-router";
import { JobDetailScreen } from "../../../src/screens/trade/JobDetailScreen";
import { MOCK_JOBS } from "../../../src/data/mockJobs";
import { MOCK_INVOICES } from "../../../src/data/mockInvoices";
import { useJobDetail, useJobActions } from "../../../src/api/jobs";
import { createAndSendInvoice } from "../../../src/api/invoices";
import { config } from "../../../src/lib/config";

export default function JobDetailRoute() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();

  // Connected mode: resolve the real job (+ raw contact id for invoicing).
  const { job: realJob, raw } = useJobDetail(id);
  const { start, complete } = useJobActions(id);
  const job = realJob ?? MOCK_JOBS.find((j) => j.id === id);

  if (!job) return null;

  const isReal = config.apiEnabled && !!raw;

  const handleSubmitInvoiceReal = async (
    lineItems: { description: string; amount: number }[]
  ) => {
    if (!raw) return;
    const invoice = await createAndSendInvoice({
      contactId: raw.customer.id,
      jobId: raw.id,
      quoteId: raw.quoteId ?? undefined,
      lineItems: lineItems.map((li) => ({
        description: li.description,
        quantity: 1,
        unitPrice: li.amount,
      })),
    });
    router.push(`/(trade)/invoice/${invoice.id}`);
  };

  const handleSubmitInvoiceMock = (
    _lineItems: { description: string; amount: number }[],
    total: number
  ) => {
    // Update (or create) the invoice for this job's customer to reflect the
    // final on-site total, then open it so the electrician can send/track it.
    const existing = MOCK_INVOICES.find((inv) => inv.quoteId === job.quoteId);
    const invoiceId = existing?.id ?? `inv-${Date.now()}`;
    if (existing) {
      existing.amount = total;
      existing.status = "sent";
      existing.sentAt = new Date().toISOString();
    } else {
      MOCK_INVOICES.push({
        id: invoiceId,
        quoteId: job.quoteId,
        customerName: job.customerName,
        title: job.title,
        amount: total,
        status: "sent",
        dueDate: new Date(Date.now() + 14 * 86400000).toISOString(),
        sentAt: new Date().toISOString(),
      });
    }
    router.push(`/(trade)/invoice/${invoiceId}`);
  };

  return (
    <JobDetailScreen
      job={job}
      onClose={() => router.back()}
      onStart={isReal ? () => start.mutateAsync().then(() => undefined) : undefined}
      onComplete={isReal ? () => complete.mutateAsync().then(() => undefined) : undefined}
      busy={start.isPending || complete.isPending}
      onSubmitInvoice={isReal ? handleSubmitInvoiceReal : handleSubmitInvoiceMock}
    />
  );
}

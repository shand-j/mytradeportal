import { useLocalSearchParams, useRouter } from "expo-router";
import { JobDetailScreen } from "../../../src/screens/trade/JobDetailScreen";
import { MOCK_JOBS } from "../../../src/data/mockJobs";
import { MOCK_INVOICES } from "../../../src/data/mockInvoices";

export default function JobDetailRoute() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const job = MOCK_JOBS.find((j) => j.id === id);

  if (!job) return null;

  const handleSubmitInvoice = (total: number) => {
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
    <JobDetailScreen job={job} onClose={() => router.back()} onSubmitInvoice={handleSubmitInvoice} />
  );
}

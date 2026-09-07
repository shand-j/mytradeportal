import { useLocalSearchParams, useRouter } from "expo-router";
import { JobDetailScreen } from "../../../src/screens/trade/JobDetailScreen";
import { useJobDetail, useJobActions } from "../../../src/api/jobs";
import { createAndSendInvoice } from "../../../src/api/invoices";

export default function JobDetailRoute() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();

  const { job: realJob, raw } = useJobDetail(id);
  const { start, complete } = useJobActions(id);

  if (!realJob || !raw) return null;

  const handleSubmitInvoice = async (
    lineItems: { description: string; amount: number }[]
  ) => {
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

  return (
    <JobDetailScreen
      job={realJob}
      onClose={() => router.back()}
      onStart={() => start.mutateAsync().then(() => undefined)}
      onComplete={() => complete.mutateAsync().then(() => undefined)}
      busy={start.isPending || complete.isPending}
      onSubmitInvoice={handleSubmitInvoice}
    />
  );
}

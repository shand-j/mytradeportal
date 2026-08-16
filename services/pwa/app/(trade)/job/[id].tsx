import { useLocalSearchParams, useRouter } from "expo-router";
import { JobDetailScreen } from "../../../src/screens/trade/JobDetailScreen";
import { MOCK_JOBS } from "../../../src/data/mockJobs";
import { MOCK_INVOICES } from "../../../src/data/mockInvoices";

export default function JobDetailRoute() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const job = MOCK_JOBS.find((j) => j.id === id);

  if (!job) return null;

  return (
    <JobDetailScreen
      job={job}
      onClose={() => router.back()}
      onCreateInvoice={() => {
        MOCK_INVOICES.push({
          id: `inv-${Date.now()}`,
          quoteId: job.quoteId,
          customerName: job.customerName,
          title: job.title,
          amount: 745,
          status: "draft",
          dueDate: new Date(Date.now() + 14 * 86400000).toISOString(),
        });
        router.back();
      }}
    />
  );
}

import { useLocalSearchParams, useRouter } from "expo-router";
import { InvoiceCreateScreen } from "../../../src/screens/trade/InvoiceCreateScreen";

export default function InvoiceCreateRoute() {
  const router = useRouter();
  const { jobId, contactId, title, customerName } = useLocalSearchParams<{
    jobId?: string;
    contactId?: string;
    title?: string;
    customerName?: string;
  }>();

  if (!contactId) {
    // The page is only reachable from a job (which always has a customer).
    router.back();
    return null;
  }

  return (
    <InvoiceCreateScreen
      jobId={jobId}
      contactId={contactId}
      jobTitle={title}
      customerName={customerName}
      onClose={() => router.back()}
    />
  );
}

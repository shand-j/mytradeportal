import { useMemo, useState } from "react";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { QuoteEditScreen } from "../../../src/screens/trade/QuoteEditScreen";
import { useQuote, useConvertQuoteToInvoice } from "../../../src/api/quotes";
import { fetchJobs, useConvertQuoteToJob } from "../../../src/api/jobs";
import { fetchInvoices } from "../../../src/api/invoices";
import { ApiError } from "../../../src/lib/apiClient";

export default function QuoteDetailRoute() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();

  const { quote: realQuote } = useQuote(id);
  const convert = useConvertQuoteToInvoice();
  const convertToJob = useConvertQuoteToJob();
  const jobsQuery = useQuery({ queryKey: ["jobs"], queryFn: () => fetchJobs() });
  const invoicesQuery = useQuery({ queryKey: ["invoices"], queryFn: fetchInvoices });
  const [jobConvertFailed, setJobConvertFailed] = useState(false);

  const existingJobId = useMemo(
    () => jobsQuery.data?.find((j) => j.quoteId === id)?.id ?? null,
    [jobsQuery.data, id]
  );

  // Once a sent (or paid) invoice exists for the quote, the backend rejects
  // edits with 409 quote_invoiced — mirror that here and show the quote
  // read-only instead of letting edits fail on save. Draft invoices don't lock.
  const invoicedReadOnly = useMemo(
    () =>
      invoicesQuery.data?.some(
        (inv) => inv.quoteId === id && (inv.status === "sent" || inv.status === "paid")
      ) ?? false,
    [invoicesQuery.data, id]
  );

  if (!realQuote) return null;

  const handleConvertToInvoice = async () => {
    const { id: invoiceId } = await convert.mutateAsync(realQuote.id);
    router.replace(`/(trade)/invoice/${invoiceId}`);
  };

  const handleConvertToJob = async () => {
    try {
      const job = await convertToJob.mutateAsync({ quoteId: realQuote.id });
      router.push(`/(trade)/job/${job.id}`);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        // A job already exists for this quote. Refresh the jobs cache so the
        // screen links to it ("View job"); when it can't be resolved, fall
        // back to the legacy convert-to-invoice path.
        const jobs = await queryClient.fetchQuery({ queryKey: ["jobs"], queryFn: () => fetchJobs() });
        if (!jobs.some((j) => j.quoteId === realQuote.id)) {
          setJobConvertFailed(true);
        }
        return;
      }
      throw err;
    }
  };

  return (
    <QuoteEditScreen
      seed={realQuote}
      onClose={() => router.back()}
      onConvertToInvoice={handleConvertToInvoice}
      onConvertToJob={handleConvertToJob}
      existingJobId={existingJobId}
      jobConvertFailed={jobConvertFailed}
      invoicedReadOnly={invoicedReadOnly}
    />
  );
}

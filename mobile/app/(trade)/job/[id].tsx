import { useMemo } from "react";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { JobDetailScreen } from "../../../src/screens/trade/JobDetailScreen";
import { useJobDetail, useJobActions, useUpdateJob } from "../../../src/api/jobs";
import { createAndSendInvoice, fetchInvoices } from "../../../src/api/invoices";
import { useQuote } from "../../../src/api/quotes";
import { useUsersList } from "../../../src/api/users";
import { useContact } from "../../../src/api/contacts";
import { startDirectThread } from "../../../src/api/communications";

export default function JobDetailRoute() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();
  const { job: realJob, raw } = useJobDetail(id);
  const { start, complete } = useJobActions(id);
  const updateJob = useUpdateJob(id);
  const { users } = useUsersList();
  const invoicesQuery = useQuery({ queryKey: ["invoices"], queryFn: fetchInvoices });
  // The job's invoice inherits the source quote's VAT rate server-side; the
  // preview must show the same rate (0% for non-VAT-registered tenants).
  const { quote: sourceQuote } = useQuote(raw?.quoteId ?? undefined);
  // Full CRM contact (preferred contact method, app-account flag) for the
  // message button's channel routing.
  const { contact } = useContact(raw?.customer.id);

  const existingInvoiceId = useMemo(
    () =>
      invoicesQuery.data?.find(
        (inv) => inv.jobId === id || (raw?.quoteId != null && inv.quoteId === raw.quoteId)
      )?.id ?? null,
    [invoicesQuery.data, id, raw?.quoteId]
  );

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
    queryClient.invalidateQueries({ queryKey: ["invoices"] });
    router.push(`/(trade)/invoice/${invoice.id}`);
  };

  const handleCreateInvoiceAi = () => {
    router.push({
      pathname: "/(trade)/invoice/new",
      params: {
        jobId: raw.id,
        contactId: raw.customer.id,
        title: raw.title,
        customerName: raw.customer.name,
      },
    });
  };

  return (
    <JobDetailScreen
      job={realJob}
      onClose={() => router.back()}
      onStart={() => start.mutateAsync().then(() => undefined)}
      onComplete={() => complete.mutateAsync().then(() => undefined)}
      busy={start.isPending || complete.isPending}
      onSubmitInvoice={handleSubmitInvoice}
      onCreateInvoiceAi={handleCreateInvoiceAi}
      existingInvoiceId={existingInvoiceId}
      vatRate={sourceQuote?.vatRate}
      onViewInvoice={
        existingInvoiceId
          ? () => router.push(`/(trade)/invoice/${existingInvoiceId}`)
          : undefined
      }
      onUpdateJob={async (patch) => {
        await updateJob.mutateAsync(patch);
      }}
      members={users.map((u) => ({ id: u.id, fullName: u.fullName }))}
      initialNotes={raw.notes}
      scheduledStart={raw.scheduledStart}
      scheduledEnd={raw.scheduledEnd}
      photos={raw.photos ?? []}
      contactEmail={contact?.email ?? raw.customer.email}
      preferredContactMethod={contact?.preferredContactMethod ?? null}
      hasAccount={contact?.hasAccount ?? false}
      onOpenChat={async () => {
        const { quoteRequestId } = await startDirectThread(raw.customer.id);
        router.push({ pathname: "/(trade)/messages", params: { quoteRequestId } });
      }}
    />
  );
}

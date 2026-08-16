import { useMemo, useState } from "react";
import { Pressable, ScrollView, TextInput, View } from "react-native";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { Icon, IconName } from "../../components/ui/Icon";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { MOCK_CUSTOMERS } from "../../data/mockCustomers";
import { MOCK_INVOICES } from "../../data/mockInvoices";
import { MOCK_JOBS } from "../../data/mockJobs";
import { MOCK_QUOTES, getQuoteTotal } from "../../data/mockQuotes";
import { Customer, Invoice, Job, Quote } from "../../types";

export type CRMScreenProps = {
  navigation?: {
    navigate: (name: string, params?: Record<string, unknown>) => void;
  };
};

export function CRMScreen(_props: CRMScreenProps) {
  const [query, setQuery] = useState("");
  const [selectedCustomer, setSelectedCustomer] = useState<Customer | null>(null);

  const filtered = useMemo(() => {
    if (!query.trim()) return MOCK_CUSTOMERS;
    return MOCK_CUSTOMERS.filter(
      (c) =>
        c.name.toLowerCase().includes(query.toLowerCase()) ||
        c.postcode.toLowerCase().includes(query.toLowerCase())
    );
  }, [query]);

  if (selectedCustomer) {
    return <CustomerDetail customer={selectedCustomer} onBack={() => setSelectedCustomer(null)} />;
  }

  return (
    <Screen>
      <Header title="Customers" />
      <ScrollView className="flex-1" contentContainerStyle={{ paddingBottom: 24, gap: 16 }}>
        <Text variant="body" color="secondary">
          Search contacts, view history, and add notes.
        </Text>
        <TextInput
          className="h-12 rounded-xl border border-gray-200 bg-white px-4 text-base text-gray-900"
          value={query}
          onChangeText={setQuery}
          placeholder="Search by name or postcode"
          placeholderTextColor="#9CA3AF"
        />

        {filtered.map((customer) => (
          <Pressable
            key={customer.id}
            testID={`customer-card-${customer.id}`}
            onPress={() => setSelectedCustomer(customer)}
          >
            <View className="gap-1 rounded-2xl border border-gray-200 bg-white p-4">
              <View className="flex-row items-center justify-between gap-2">
                <Text variant="body" weight="semibold" numberOfLines={1} style={{ flex: 1 }}>
                  {customer.name}
                </Text>
                <Text variant="caption" color="secondary">
                  £{customer.lifetimeValue.toFixed(0)}
                </Text>
              </View>
              <Text variant="caption" color="secondary">
                {customer.postcode} · {customer.quoteCount} quotes · {customer.jobCount} jobs
              </Text>
            </View>
          </Pressable>
        ))}
      </ScrollView>
    </Screen>
  );
}

type CustomerDetailView = "summary" | "quotes" | "jobs" | "invoices";

function CustomerDetail({ customer, onBack }: { customer: Customer; onBack: () => void }) {
  const [view, setView] = useState<CustomerDetailView>("summary");

  const quotes = useMemo(
    () => MOCK_QUOTES.filter((q) => q.customerName === customer.name),
    [customer.name]
  );
  const jobs = useMemo(
    () => MOCK_JOBS.filter((j) => j.customerName === customer.name),
    [customer.name]
  );
  const invoices = useMemo(
    () => MOCK_INVOICES.filter((inv) => inv.customerName === customer.name),
    [customer.name]
  );

  return (
    <Screen>
      <Header
        title={customer.name}
        onBack={() => (view === "summary" ? onBack() : setView("summary"))}
      />
      <Text variant="caption" color="secondary">
        {customer.postcode} · {customer.address}
      </Text>

      <ScrollView className="flex-1" contentContainerStyle={{ paddingBottom: 24, gap: 16 }}>
        {view === "summary" && (
          <>
            <View className="gap-2 rounded-2xl border border-gray-200 bg-white p-4">
              <Text variant="body" weight="semibold">
                Contact
              </Text>
              <Text variant="body">{customer.email}</Text>
              <Text variant="body">{customer.phone}</Text>
            </View>

            <View className="gap-2 rounded-2xl border border-gray-200 bg-white p-4">
              <Text variant="body" weight="semibold">
                History
              </Text>
              <Text variant="caption" color="secondary">
                Lifetime value: £{customer.lifetimeValue.toFixed(2)}
              </Text>
              <Text variant="caption" color="secondary">
                Last contact: {new Date(customer.lastContact).toLocaleDateString()}
              </Text>
            </View>

            <View className="flex-row flex-wrap gap-2">
              <HistoryLink icon="quotes" label={`Quotes (${quotes.length})`} onPress={() => setView("quotes")} />
              <HistoryLink icon="dashboard" label={`Jobs (${jobs.length})`} onPress={() => setView("jobs")} />
              <HistoryLink icon="info" label={`Invoices (${invoices.length})`} onPress={() => setView("invoices")} />
            </View>

            <View className="gap-2 rounded-2xl border border-gray-200 bg-white p-4">
              <Text variant="body" weight="semibold">
                Notes
              </Text>
              <Text variant="body" color="secondary">
                {customer.notes}
              </Text>
            </View>

            <View className="flex-row gap-3">
              <Button title="Add note" variant="outline" onPress={() => {}} />
              <Button title="Edit details" variant="outline" onPress={() => {}} />
            </View>
          </>
        )}

        {view === "quotes" && <CustomerQuotesView quotes={quotes} customer={customer} onBack={() => setView("summary")} />}
        {view === "jobs" && <CustomerJobsView jobs={jobs} customer={customer} onBack={() => setView("summary")} />}
        {view === "invoices" && <CustomerInvoicesView invoices={invoices} customer={customer} onBack={() => setView("summary")} />}
      </ScrollView>
    </Screen>
  );
}

function HistoryLink({ icon, label, onPress }: { icon: IconName; label: string; onPress: () => void }) {
  return (
    <Pressable onPress={onPress}>
      <View className="flex-row items-center gap-1.5 rounded-xl border border-blue-200 bg-blue-50 px-3 py-2">
        <Icon name={icon} size={18} color="#2563EB" />
        <Text variant="caption" color="primary">
          {label}
        </Text>
      </View>
    </Pressable>
  );
}

function CustomerQuotesView({ quotes, customer, onBack }: { quotes: Quote[]; customer: Customer; onBack: () => void }) {
  return (
    <View className="gap-3">
      <Text variant="body" weight="semibold">
        Quotes for {customer.name}
      </Text>
      {quotes.length === 0 && (
        <Text variant="body" color="secondary">
          No quotes yet.
        </Text>
      )}
      {quotes.map((quote) => {
        const totals = getQuoteTotal(quote);
        return (
          <View key={quote.id} className="gap-2 rounded-2xl border border-gray-200 bg-white p-4">
            <Text variant="body" weight="semibold">
              {quote.title}
            </Text>
            <Text variant="caption" color="secondary">
              {quote.postcode} · {quote.status}
            </Text>
            <Text variant="body" weight="semibold">
              £{totals.total.toFixed(2)} inc VAT
            </Text>
          </View>
        );
      })}
      <Button title="Back to customer" variant="outline" onPress={onBack} />
    </View>
  );
}

function CustomerJobsView({ jobs, customer, onBack }: { jobs: Job[]; customer: Customer; onBack: () => void }) {
  return (
    <View className="gap-3">
      <Text variant="body" weight="semibold">
        Jobs for {customer.name}
      </Text>
      {jobs.length === 0 && (
        <Text variant="body" color="secondary">
          No jobs yet.
        </Text>
      )}
      {jobs.map((job) => (
        <View key={job.id} className="gap-2 rounded-2xl border border-gray-200 bg-white p-4">
          <Text variant="body" weight="semibold">
            {job.title}
          </Text>
          <Text variant="caption" color="secondary">
            {job.date} · {job.time}
          </Text>
          <Text variant="caption" color="secondary">
            {job.postcode} · {job.status} · {job.assignedTo}
          </Text>
        </View>
      ))}
      <Button title="Back to customer" variant="outline" onPress={onBack} />
    </View>
  );
}

function CustomerInvoicesView({ invoices, customer, onBack }: { invoices: Invoice[]; customer: Customer; onBack: () => void }) {
  return (
    <View className="gap-3">
      <Text variant="body" weight="semibold">
        Invoices for {customer.name}
      </Text>
      {invoices.length === 0 && (
        <Text variant="body" color="secondary">
          No invoices yet.
        </Text>
      )}
      {invoices.map((invoice) => (
        <View key={invoice.id} className="gap-2 rounded-2xl border border-gray-200 bg-white p-4">
          <Text variant="body" weight="semibold">
            {invoice.title}
          </Text>
          <Text variant="caption" color="secondary">
            {invoice.status} · Due {new Date(invoice.dueDate).toLocaleDateString()}
          </Text>
          <Text variant="body" weight="semibold">
            £{invoice.amount.toFixed(2)}
          </Text>
        </View>
      ))}
      <Button title="Back to customer" variant="outline" onPress={onBack} />
    </View>
  );
}

import { useMemo, useState } from "react";
import { Pressable, ScrollView, TextInput, View } from "react-native";
import { useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { Contact, useContactsList } from "../../api/contacts";
import { ApiQuote, fetchQuotes } from "../../api/quotes";
import { ApiQuoteRequest, fetchLeads } from "../../api/quoteRequests";
import { SettingsMenuButton } from "../../components/ui/SettingsMenuButton";
import { CustomerBadges } from "../../components/trade/CustomerBadges";
import { formatDateUK } from "../../lib/format";

export type CRMScreenProps = {
  navigation?: {
    navigate: (name: string, params?: Record<string, unknown>) => void;
  };
};

export function CRMScreen(_props: CRMScreenProps) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const { contacts, isLoading, error } = useContactsList();

  // Leads and quotes are matched to contacts by their nested customer id.
  const { data: quoteRequests } = useQuery({ queryKey: ["quote-requests"], queryFn: fetchLeads });
  const { data: quotes } = useQuery({ queryKey: ["quotes"], queryFn: fetchQuotes });

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const sorted = [...contacts].sort((a, b) => a.name.localeCompare(b.name));
    if (!q) return sorted;
    return sorted.filter((c) =>
      [c.name, c.email, c.phone, c.postcode].some((field) => field?.toLowerCase().includes(q))
    );
  }, [contacts, query]);

  return (
    <Screen>
      <Header title="Customers" rightAction={<SettingsMenuButton />} />
      <ScrollView
        className="flex-1"
        style={{ minHeight: 0 }}
        contentContainerStyle={{ paddingBottom: 24, gap: 16 }}
      >
        <Text variant="body" color="secondary">
          Search contacts, view history, and add notes.
        </Text>
        <Button
          testID="customers-new-customer"
          title="New Customer"
          onPress={() => router.push("/(trade)/manual-lead")}
        />
        <TextInput
          testID="customers-search"
          className="h-12 rounded-xl border border-gray-200 bg-white px-4 text-base text-gray-900"
          value={query}
          onChangeText={setQuery}
          placeholder="Search by name or postcode"
          placeholderTextColor="#9CA3AF"
        />

        {isLoading && (
          <Text variant="caption" color="secondary" align="center">
            Loading customers…
          </Text>
        )}

        {!!error && (
          <View className="rounded-2xl border border-amber-200 bg-amber-50 p-4">
            <Text variant="caption" color="warning" align="center">
              Could not load customers. Please try again.
            </Text>
          </View>
        )}

        {!isLoading && !error && filtered.length === 0 && (
          <View className="gap-3 rounded-2xl bg-gray-100 p-6">
            <Text variant="body" align="center" color="secondary">
              {query ? "No customers match your search." : "No customers yet."}
            </Text>
            <Text variant="caption" align="center" color="secondary">
              Contacts appear here automatically when a homeowner requests a quote.
            </Text>
          </View>
        )}

        {filtered.map((contact) => (
          <ContactCard
            key={contact.id}
            contact={contact}
            expanded={expandedId === contact.id}
            onPress={() => setExpandedId((prev) => (prev === contact.id ? null : contact.id))}
            leads={(quoteRequests ?? []).filter((qr) => qr.customer?.id === contact.id)}
            quotes={(quotes ?? []).filter((q) => q.customer?.id === contact.id)}
            onOpenLead={(id) => router.push(`/(trade)/lead/${id}`)}
            onOpenQuote={(id) => router.push(`/(trade)/quote/${id}`)}
            onOpenDetail={() => router.push(`/(trade)/customer/${contact.id}`)}
            onCreateQuote={() =>
              router.push(
                `/(trade)/quote-intake?contactId=${contact.id}&contactName=${encodeURIComponent(contact.name)}`
              )
            }
          />
        ))}
      </ScrollView>
    </Screen>
  );
}

function ContactCard({
  contact,
  expanded,
  onPress,
  leads,
  quotes,
  onOpenLead,
  onOpenQuote,
  onOpenDetail,
  onCreateQuote,
}: {
  contact: Contact;
  expanded: boolean;
  onPress: () => void;
  leads: ApiQuoteRequest[];
  quotes: ApiQuote[];
  onOpenLead: (id: string) => void;
  onOpenQuote: (id: string) => void;
  onOpenDetail: () => void;
  onCreateQuote: () => void;
}) {
  const subtitle = [contact.phone, contact.email, contact.postcode].filter(Boolean).join(" · ");
  return (
    <Pressable testID={`contact-card-${contact.id}`} onPress={onPress}>
      <View className="gap-1 rounded-2xl border border-gray-200 bg-white p-4">
        <Text variant="body" weight="semibold" numberOfLines={1}>
          {contact.name}
        </Text>
        {subtitle.length > 0 && (
          <Text variant="caption" color="secondary">
            {subtitle}
          </Text>
        )}
        <CustomerBadges badges={contact.badges ?? []} isBlocked={contact.isBlocked} />
        {expanded && (
          <View className="mt-2 gap-2 border-t border-gray-100 pt-2">
            {contact.address ? (
              <Text variant="caption" color="secondary">
                {contact.address}
              </Text>
            ) : null}
            <Text variant="caption" color="secondary">
              Customer since {formatDateUK(contact.createdAt)}
            </Text>
            {contact.notes ? (
              <Text variant="caption" color="secondary">
                Notes: {contact.notes}
              </Text>
            ) : null}

            {leads.length > 0 && (
              <View className="gap-1 pt-1">
                <Text variant="caption" weight="semibold">
                  Leads
                </Text>
                {leads.map((lead) => (
                  <Pressable key={lead.id} onPress={() => onOpenLead(lead.id)}>
                    <Text variant="caption" color="primary">
                      {(lead.structuredData?.title as string) || lead.rawText?.slice(0, 60) || "Lead"} ·{" "}
                      {formatDateUK(lead.createdAt)}
                    </Text>
                  </Pressable>
                ))}
              </View>
            )}

            {quotes.length > 0 && (
              <View className="gap-1 pt-1">
                <Text variant="caption" weight="semibold">
                  Quotes
                </Text>
                {quotes.map((quote) => (
                  <Pressable key={quote.id} onPress={() => onOpenQuote(quote.id)}>
                    <Text variant="caption" color="primary">
                      {quote.title} · {quote.status}
                    </Text>
                  </Pressable>
                ))}
              </View>
            )}

            {leads.length === 0 && quotes.length === 0 && (
              <Text variant="caption" color="secondary">
                No leads or quotes yet.
              </Text>
            )}

            <View className="pt-1 gap-2">
              <Button
                testID={`contact-open-detail-${contact.id}`}
                title="View & edit"
                size="sm"
                onPress={onOpenDetail}
              />
              <Button
                testID={`contact-create-quote-${contact.id}`}
                title="Create quote"
                size="sm"
                variant="outline"
                onPress={onCreateQuote}
              />
            </View>
          </View>
        )}
      </View>
    </Pressable>
  );
}

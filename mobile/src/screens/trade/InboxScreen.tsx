import { useMemo, useState } from "react";
import { Alert, Pressable, ScrollView, TextInput, View } from "react-native";
import { useRouter } from "expo-router";
import { Header } from "../../components/ui/Header";
import { Icon } from "../../components/ui/Icon";
import { IconButton } from "../../components/ui/IconButton";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { SettingsMenuButton } from "../../components/ui/SettingsMenuButton";
import { useLeadsList } from "../../api/quoteRequests";
import { Contact, useContactsList } from "../../api/contacts";
import { startDirectThread } from "../../api/communications";
import { ApiError } from "../../lib/apiClient";
import { Lead } from "../../types";

function InboxRow({ lead, onPress }: { lead: Lead; onPress: () => void }) {
  const meta = [lead.customerName, lead.urgency.replace(/_/g, " "), lead.status]
    .filter(Boolean)
    .join(" · ");
  return (
    <Pressable testID={`inbox-lead-${lead.id}`} onPress={onPress}>
      <View className="gap-1 rounded-2xl border border-gray-200 bg-white p-4">
        <Text variant="body" weight="semibold" numberOfLines={1}>
          {lead.title}
        </Text>
        <Text variant="caption" color="secondary" numberOfLines={1}>
          {meta}
        </Text>
      </View>
    </Pressable>
  );
}

/** Searchable list of CRM customers with app accounts (new-message picker). */
function NewMessagePicker({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const { contacts, isLoading } = useContactsList(true);
  const [query, setQuery] = useState("");
  const [startingContactId, setStartingContactId] = useState<string | null>(null);

  const matches = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return contacts;
    return contacts.filter((contact) =>
      [contact.name, contact.email ?? "", contact.phone ?? ""]
        .join(" ")
        .toLowerCase()
        .includes(needle)
    );
  }, [contacts, query]);

  const openThread = async (contact: Contact) => {
    setStartingContactId(contact.id);
    try {
      const { quoteRequestId } = await startDirectThread(contact.id);
      router.push({ pathname: "/(trade)/messages", params: { quoteRequestId } });
    } catch (err) {
      Alert.alert(
        "Couldn't open the conversation",
        err instanceof ApiError ? err.detail : "Please try again."
      );
      setStartingContactId(null);
    }
  };

  return (
    <Screen>
      <Header title="New message" onBack={onClose} />
      <TextInput
        testID="new-message-search"
        className="mb-3 h-12 rounded-xl border border-slate-200 bg-slate-50 px-4 text-base text-slate-900"
        value={query}
        onChangeText={setQuery}
        placeholder="Search customers…"
        placeholderTextColor="#94A3B8"
        autoCapitalize="none"
        autoCorrect={false}
      />
      <ScrollView className="flex-1" contentContainerStyle={{ paddingBottom: 24, gap: 12 }}>
        {isLoading && (
          <Text variant="caption" color="secondary" align="center">
            Loading customers…
          </Text>
        )}

        {!isLoading && contacts.length === 0 && (
          <View className="gap-2 rounded-2xl bg-gray-100 p-6">
            <Text variant="body" align="center" color="secondary">
              No customers have the app yet — invite them from their customer page first.
            </Text>
          </View>
        )}

        {!isLoading && contacts.length > 0 && matches.length === 0 && (
          <Text variant="caption" color="secondary" align="center">
            No customers match "{query}".
          </Text>
        )}

        {matches.map((contact) => (
          <Pressable
            key={contact.id}
            testID={`new-message-contact-${contact.id}`}
            disabled={startingContactId !== null}
            onPress={() => void openThread(contact)}
          >
            <View className="flex-row items-center gap-3 rounded-2xl border border-gray-200 bg-white p-4">
              <View className="h-9 w-9 items-center justify-center rounded-full bg-slate-100">
                <Icon name="profile" size={18} color="#374151" />
              </View>
              <View className="flex-1">
                <Text variant="body" weight="semibold" numberOfLines={1}>
                  {contact.name}
                </Text>
                <Text variant="caption" color="secondary" numberOfLines={1}>
                  {startingContactId === contact.id
                    ? "Opening conversation…"
                    : (contact.email ?? contact.phone ?? "")}
                </Text>
              </View>
              <Icon name="messages" size={18} color="#374151" />
            </View>
          </Pressable>
        ))}
      </ScrollView>
    </Screen>
  );
}

export function InboxScreen() {
  const router = useRouter();
  const { leads, isLoading } = useLeadsList();
  const [composing, setComposing] = useState(false);

  if (composing) {
    return <NewMessagePicker onClose={() => setComposing(false)} />;
  }

  return (
    <Screen>
      <Header
        title="Messages"
        rightAction={
          <View className="flex-row items-center gap-2">
            <IconButton
              testID="new-message-button"
              icon="plus"
              size={22}
              color="#374151"
              onPress={() => setComposing(true)}
              accessibilityLabel="New message"
            />
            <SettingsMenuButton />
          </View>
        }
      />
      <ScrollView className="flex-1" contentContainerStyle={{ paddingBottom: 24, gap: 12 }}>
        {isLoading && (
          <Text variant="caption" color="secondary" align="center">
            Loading conversations…
          </Text>
        )}

        {!isLoading && leads.length === 0 && (
          <View className="gap-2 rounded-2xl bg-gray-100 p-6">
            <Text variant="body" align="center" color="secondary">
              No conversations yet — new quote requests will appear here.
            </Text>
          </View>
        )}

        {leads.map((lead) => (
          <InboxRow
            key={lead.id}
            lead={lead}
            onPress={() =>
              router.push({
                pathname: "/(trade)/messages",
                params: { quoteRequestId: lead.id },
              })
            }
          />
        ))}
      </ScrollView>
    </Screen>
  );
}

import { Pressable, ScrollView, View } from "react-native";
import { useRouter } from "expo-router";
import { Header } from "../../components/ui/Header";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { SettingsMenuButton } from "../../components/ui/SettingsMenuButton";
import { useLeadsList } from "../../api/quoteRequests";
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

export function InboxScreen() {
  const router = useRouter();
  const { leads, isLoading } = useLeadsList();

  return (
    <Screen>
      <Header title="Messages" rightAction={<SettingsMenuButton />} />
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

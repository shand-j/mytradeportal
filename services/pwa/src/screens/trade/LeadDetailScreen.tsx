import { useState } from "react";
import { Alert, Image, ScrollView, View } from "react-native";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { Icon } from "../../components/ui/Icon";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { getLeadSourceLabel } from "../../data/mockLeads";
import { MOCK_MEDIA } from "../../data/mockMedia";
import { Lead } from "../../types";

export type LeadDetailScreenProps = {
  lead: Lead;
  onBack: () => void;
  onGenerateQuote: (lead: Lead) => void;
  onRequestSiteVisit: (lead: Lead) => void;
  onMarkDead?: (lead: Lead) => void;
};

export function LeadDetailScreen({
  lead,
  onBack,
  onGenerateQuote,
  onRequestSiteVisit,
  onMarkDead,
}: LeadDetailScreenProps) {
  const [dead, setDead] = useState(false);
  const media = lead.mediaIds?.map((id) => MOCK_MEDIA.find((m) => m.id === id)).filter(Boolean) ?? [];

  const handleMarkDead = () => {
    Alert.alert("Mark as dead?", "This lead will be hidden from the list.", [
      { text: "Cancel", style: "cancel" },
      {
        text: "Mark dead",
        style: "destructive",
        onPress: () => {
          setDead(true);
          onMarkDead?.(lead);
          onBack();
        },
      },
    ]);
  };

  if (dead) {
    return (
      <Screen>
        <Header title="Lead detail" onBack={onBack} />
        <View className="flex-1 items-center justify-center px-6">
          <Text variant="body" color="secondary" align="center">
            Lead marked as dead.
          </Text>
          <Button title="Back to leads" variant="outline" onPress={onBack} />
        </View>
      </Screen>
    );
  }

  return (
    <Screen>
      <Header testID="lead-detail-back" title="Lead detail" onBack={onBack} />

      <ScrollView className="flex-1" contentContainerClassName="gap-4 pb-6">
        <View className="rounded-2xl bg-slate-100 p-4 gap-2">
          <View className="flex-row items-center justify-between gap-3">
            <Text variant="body" weight="semibold" className="flex-1" numberOfLines={1}>
              {lead.title}
            </Text>
            <View
              className={`rounded-lg px-2 py-1 ${
                lead.badge === "Flagged" ? "bg-amber-100" : "bg-blue-100"
              }`}
            >
              <Text variant="caption" color="secondary">
                {lead.badge.toUpperCase()}
              </Text>
            </View>
          </View>
          <Text variant="caption" color="secondary">
            {getLeadSourceLabel(lead.source)} · {lead.postcode} · {lead.urgency}
          </Text>
          <Text variant="caption" color="secondary">
            Received {new Date(lead.createdAt).toLocaleDateString()}
          </Text>
          {lead.estimate && (
            <Text variant="body" weight="semibold">
              Estimate: {lead.estimate}
            </Text>
          )}
        </View>

        <View className="rounded-2xl bg-slate-100 p-4 gap-2">
          <Text variant="body" weight="semibold">
            Customer
          </Text>
          <Text variant="body">{lead.customerName}</Text>
          {lead.customerPhone && <Text variant="caption" color="secondary">{lead.customerPhone}</Text>}
          {lead.customerEmail && <Text variant="caption" color="secondary">{lead.customerEmail}</Text>}
        </View>

        {lead.note && (
          <View className="rounded-2xl bg-slate-100 p-4 gap-2">
            <Text variant="body" weight="semibold">
              Notes
            </Text>
            <Text variant="body" color="secondary">
              {lead.note}
            </Text>
          </View>
        )}

        {media.length > 0 && (
          <View className="rounded-2xl bg-slate-100 p-4 gap-3">
            <Text variant="body" weight="semibold">
              Photos / videos
            </Text>
            <View className="flex-row flex-wrap gap-3">
              {media.map((item) =>
                item?.type === "image" && item.uri ? (
                  <View key={item.id} className="w-20 h-20 rounded-xl overflow-hidden bg-slate-200">
                    <Image source={{ uri: item.uri }} className="w-full h-full" resizeMode="cover" />
                  </View>
                ) : (
                  <View
                    key={item?.id}
                    className="w-20 h-20 rounded-xl bg-slate-200 items-center justify-center gap-1 p-2"
                  >
                    <Icon name={item?.type === "video" ? "video" : "image"} size={20} color="#6B7280" />
                    <Text variant="caption" color="secondary" numberOfLines={1}>
                      {item?.caption ?? item?.type}
                    </Text>
                  </View>
                )
              )}
            </View>
          </View>
        )}

        <View className="gap-3 pt-2">
          <Button title="Generate AI quote" onPress={() => onGenerateQuote(lead)} />
          <Button
            testID="lead-request-info"
            title="Request more info"
            variant="outline"
            onPress={() => onRequestSiteVisit(lead)}
          />
          <Button title="Mark as dead" variant="outline" onPress={handleMarkDead} />
        </View>
      </ScrollView>
    </Screen>
  );
}

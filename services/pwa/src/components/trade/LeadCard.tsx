import { Pressable, View } from "react-native";
import { Text } from "../ui/Text";
import { Lead } from "../../types";
import { getLeadSourceLabel } from "../../data/mockLeads";

type LeadCardProps = {
  lead: Lead;
  onPress: () => void;
};

export function LeadCard({ lead, onPress }: LeadCardProps) {
  const isFlagged = lead.badge === "Flagged";
  return (
    <Pressable onPress={onPress}>
      <View className="gap-2 rounded-2xl border border-gray-200 bg-white p-4">
        <View className="flex-row items-center justify-between gap-2">
          <Text variant="body" weight="semibold" numberOfLines={1} style={{ flex: 1 }}>
            {lead.title}
          </Text>
          <View className={`rounded-lg px-2 py-0.5 ${isFlagged ? "bg-amber-100" : "bg-blue-100"}`}>
            <Text variant="caption" color="secondary">
              {lead.badge.toUpperCase()}
            </Text>
          </View>
        </View>
        <Text variant="caption" color="secondary">
          {getLeadSourceLabel(lead.source)} · {lead.postcode} · {lead.urgency}
        </Text>
        <Text variant="body" weight="semibold">
          {lead.estimate}
        </Text>
      </View>
    </Pressable>
  );
}

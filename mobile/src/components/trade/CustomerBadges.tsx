import { View } from "react-native";
import { Text } from "../ui/Text";
import { TRUST_BADGES } from "../../api/contacts";

const BADGE_LABELS: Record<string, string> = Object.fromEntries(
  TRUST_BADGES.map((b) => [b.key, b.label])
);

export type CustomerBadgesProps = {
  badges: string[];
  isBlocked?: boolean;
};

/**
 * Subtle trust-badge chips for CRM rows and the customer detail header (N26).
 * Blocked renders first in amber; trust badges are quiet slate pills.
 */
export function CustomerBadges({ badges, isBlocked }: CustomerBadgesProps) {
  if (!isBlocked && badges.length === 0) return null;
  return (
    <View className="flex-row flex-wrap gap-1 pt-1">
      {isBlocked && (
        <View testID="badge-blocked" className="rounded-full bg-amber-100 px-2 py-0.5">
          <Text variant="label" color="warning" weight="semibold">
            Blocked
          </Text>
        </View>
      )}
      {badges.map((badge) => (
        <View
          key={badge}
          testID={`badge-${badge}`}
          className="rounded-full bg-slate-200 px-2 py-0.5"
        >
          <Text variant="label" color="secondary" weight="medium">
            {BADGE_LABELS[badge] ?? badge}
          </Text>
        </View>
      ))}
    </View>
  );
}

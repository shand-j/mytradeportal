import { View } from "react-native";
import { Text } from "./Text";

export type VerificationStatus =
  | "verified"
  | "pending"
  | "manual_review"
  | "self_declared"
  | "failed";

const statusConfig: Record<
  VerificationStatus,
  { label: string; bgClass: string; color: string }
> = {
  verified: { label: "Verified", bgClass: "bg-emerald-100", color: "#047857" },
  pending: { label: "Pending", bgClass: "bg-amber-100", color: "#B45309" },
  manual_review: { label: "Manual review", bgClass: "bg-slate-200", color: "#374151" },
  self_declared: { label: "Self declared", bgClass: "bg-slate-100", color: "#4B5563" },
  failed: { label: "Failed", bgClass: "bg-red-100", color: "#DC2626" },
};

export function VerificationBadge({
  status,
  label,
}: {
  status: VerificationStatus;
  label?: string;
}) {
  const config = statusConfig[status];

  return (
    <View
      className={`self-start rounded-full px-2 py-1 ${config.bgClass}`}
      testID="verification-badge"
    >
      <Text variant="caption" weight="semibold" style={{ color: config.color }}>
        {label ?? config.label}
      </Text>
    </View>
  );
}

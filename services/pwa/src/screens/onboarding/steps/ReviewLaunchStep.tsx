import { ScrollView, View } from "react-native";
import { Button } from "../../../components/ui/Button";
import { Text } from "../../../components/ui/Text";
import { VerificationBadge } from "../../../components/ui/VerificationBadge";
import {
  ChecklistItem,
  LaunchGateChecklist,
} from "../../../components/onboarding/LaunchGateChecklist";

type ReviewLaunchStepProps = {
  data?: Record<string, unknown>;
  onNext: (data?: Record<string, unknown>) => void;
};

const LAUNCH_GATE_ITEMS: ChecklistItem[] = [
  { key: "account", label: "Account created", status: "complete" },
  { key: "identity", label: "Business identity", status: "complete" },
  { key: "address", label: "Address & service area", status: "complete" },
  { key: "tax", label: "Tax & VAT", status: "complete" },
  { key: "compliance", label: "Compliance & credentials", status: "complete" },
  { key: "services", label: "Services offered", status: "complete" },
  { key: "team", label: "Team & capacity", status: "pending" },
  { key: "pricing", label: "Pricing setup", status: "pending" },
  { key: "quotes", label: "Quote defaults", status: "pending" },
  { key: "branding", label: "Branding", status: "pending" },
  { key: "payments", label: "Payments", status: "pending" },
  { key: "data-import", label: "Data import", status: "pending" },
];

const PREVIEW_SERVICES = [
  "Consumer unit",
  "EICR",
  "EV charger",
  "Additional sockets / lights",
  "Emergency callout",
];

export function ReviewLaunchStep({ onNext }: ReviewLaunchStepProps) {
  return (
    <ScrollView className="flex-1">
      <View className="gap-4 pb-6">
        <Text variant="title" weight="bold">
          Review & launch
        </Text>
        <Text variant="body" color="secondary">
          Check the details below, then launch your white-label customer quote experience.
        </Text>

        <LaunchGateChecklist items={LAUNCH_GATE_ITEMS} />

        <View className="gap-3 rounded-2xl bg-slate-100 p-4">
          <Text variant="body" weight="semibold">
            Compliance summary
          </Text>
          <View className="flex-row flex-wrap gap-2">
            <VerificationBadge status="verified" label="CH verified" />
            <VerificationBadge status="verified" label="CPS verified" />
          </View>
          <Text variant="caption" color="secondary">
            Public liability insurance valid until 2027-08-15
          </Text>
        </View>

        <View className="gap-3 rounded-2xl border border-slate-200 bg-white p-4">
          <Text variant="body" weight="semibold">
            Preview your customer quote form
          </Text>
          <Text variant="body" color="secondary">
            Customers will see a branded form with your colours, trading name, and the services
            you offer. Requests arrive as draft quotes you can review and send in seconds.
          </Text>
          <View className="rounded-xl bg-slate-50 p-3">
            <Text variant="caption" color="secondary">
              Services shown:
            </Text>
            <Text variant="body">
              {PREVIEW_SERVICES.join(" • ")}
            </Text>
          </View>
        </View>

        <Button title="Launch my business" onPress={() => onNext()} />
      </View>
    </ScrollView>
  );
}

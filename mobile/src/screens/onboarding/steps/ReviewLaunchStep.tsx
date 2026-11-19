import { ScrollView, View } from "react-native";
import { Button } from "../../../components/ui/Button";
import { Text } from "../../../components/ui/Text";
import {
  ChecklistItem,
  LaunchGateChecklist,
} from "../../../components/onboarding/LaunchGateChecklist";

type ReviewLaunchStepProps = {
  data?: Record<string, unknown>;
  onNext: (data?: Record<string, unknown>) => void;
};

/**
 * The checklist is driven by the wizard data actually collected so far: an
 * item only shows "Done" when its step's data is present (branding can also
 * be honestly "skipped"). Bank details, card payments and plan come AFTER
 * this step in the wizard, so they truthfully stay "To do" here. In resume
 * mode (data.__resume) the tenant already exists server-side, so the account
 * item is complete even though the local wizard never collected it. Items
 * with no wizard step (team, pricing, quote defaults, data import) are not
 * listed — there is no state to track them against.
 */
function buildChecklist(data: Record<string, unknown> | undefined): ChecklistItem[] {
  const has = (key: string) => Boolean(data?.[key]);
  const branding = (data?.branding ?? {}) as Record<string, unknown>;
  return [
    {
      key: "account",
      label: "Account created",
      status: has("account") || data?.__resume === true ? "complete" : "pending",
    },
    { key: "identity", label: "Business identity", status: has("identity") ? "complete" : "pending" },
    { key: "address", label: "Address & service area", status: has("address") ? "complete" : "pending" },
    { key: "tax", label: "Tax & VAT", status: has("tax") ? "complete" : "pending" },
    {
      key: "compliance",
      label: "Compliance & credentials",
      status: has("compliance") ? "complete" : "pending",
    },
    { key: "services", label: "Services offered", status: has("services") ? "complete" : "pending" },
    {
      key: "branding",
      label: "Branding",
      status: branding.skipped ? "skipped" : has("branding") ? "complete" : "pending",
    },
    // Post-review wizard steps — genuinely still to do at this point.
    {
      key: "bank_details",
      label: "Bank details",
      status: has("bank_details") ? "complete" : "pending",
    },
    {
      key: "card_payments",
      label: "Card payments",
      status: has("card_payments") ? "complete" : "pending",
    },
    { key: "plan", label: "Plan", status: has("plan") ? "complete" : "pending" },
  ];
}

const SCHEME_LABELS: Record<string, string> = {
  niceic: "NICEIC",
  napit: "NAPIT",
  elecsa: "Elecsa",
  stroma: "Stroma",
  besca: "Besca",
  select_scotland: "Select Scotland",
};

const COVER_LABELS: Record<string, string> = {
  "1000000": "£1m",
  "2000000": "£2m",
  "5000000": "£5m",
  "10000000": "£10m",
};

export function ReviewLaunchStep({ data, onNext }: ReviewLaunchStepProps) {
  const compliance = (data?.compliance ?? {}) as Record<string, unknown>;
  const services = (data?.services ?? {}) as Record<string, unknown>;
  const serviceList = (services.services as string[] | undefined) ?? [];

  const scheme = (compliance.scheme as string) ?? "";
  const membership = (compliance.membership as string) ?? "";
  const bs7671 = Boolean(compliance.bs7671);
  const inspection = Boolean(compliance.inspection);
  const insurer = (compliance.insurer as string) ?? "";
  const policyNumber = (compliance.policyNumber as string) ?? "";
  const cover = (compliance.cover as string) ?? "";
  const expiry = (compliance.expiry as string) ?? "";

  return (
    <ScrollView className="flex-1" keyboardShouldPersistTaps="handled">
      <View className="gap-4 pb-6">
        <Text variant="title" weight="bold">
          Review & launch
        </Text>
        <Text variant="body" color="secondary">
          Check the details below, then choose your plan to go live.
        </Text>

        <LaunchGateChecklist items={buildChecklist(data)} />

        <View className="gap-3 rounded-2xl bg-slate-100 p-4">
          <Text variant="body" weight="semibold">
            Compliance summary
          </Text>
          {scheme && scheme !== "none_yet" ? (
            <View className="gap-1">
              <Text variant="body">
                CPS: {SCHEME_LABELS[scheme] ?? scheme} {membership && `(${membership})`}
              </Text>
              {bs7671 && <Text variant="caption" color="secondary">18th Edition held</Text>}
              {inspection && <Text variant="caption" color="secondary">Inspection & testing (2391)</Text>}
            </View>
          ) : (
            <Text variant="caption" color="secondary">
              No Competent Person Scheme selected — customer-facing quotes are locked until verified.
            </Text>
          )}
          {insurer ? (
            <View className="gap-1">
              <Text variant="body">
                Public liability: {insurer} {policyNumber && `- ${policyNumber}`}
              </Text>
              {cover && <Text variant="caption" color="secondary">Cover: {COVER_LABELS[cover] ?? cover}</Text>}
              {expiry && <Text variant="caption" color="secondary">Expires: {expiry}</Text>}
            </View>
          ) : (
            <Text variant="caption" color="secondary">
              No public liability insurance added yet.
            </Text>
          )}
        </View>

        {serviceList.length > 0 && (
          <View className="gap-3 rounded-2xl bg-slate-100 p-4">
            <Text variant="body" weight="semibold">
              Services offered
            </Text>
            <Text variant="body">
              {serviceList.map((s) => s.replace(/_/g, " ")).join(" · ")}
            </Text>
          </View>
        )}

        <Button testID="onboarding-choose-plan" title="Choose your plan" onPress={() => onNext()} />
      </View>
    </ScrollView>
  );
}

import { ReactNode, useState } from "react";
import { Alert, Linking, ScrollView, View } from "react-native";
import { useQuery } from "@tanstack/react-query";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { fetchCommunications } from "../../api/communications";
import { getLeadSourceLabel } from "../../lib/leadSource";
import { formatDateUK, formatUrgency } from "../../lib/format";
import { useBusiness } from "../../theme/ThemeProvider";
import { Lead } from "../../types";

/** "property_type" / "propertyType" -> "Property Type". */
function humanizeKey(key: string): string {
  const spaced = key.replace(/_/g, " ").replace(/([a-z0-9])([A-Z])/g, "$1 $2");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/** Scalar display value, or null when the value should be skipped. */
function scalarText(value: unknown): string | null {
  if (value == null) return null;
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") return String(value);
  if (typeof value === "string") {
    const trimmed = value.trim();
    return trimmed ? trimmed.replace(/_/g, " ") : null;
  }
  return null;
}

function CapturedRows({ data, depth = 0 }: { data: Record<string, unknown>; depth?: number }) {
  const rows: ReactNode[] = [];
  Object.entries(data).forEach(([key, value]) => {
    if (value == null) return;
    const label = humanizeKey(key);
    if (Array.isArray(value)) {
      const scalars = value.map(scalarText).filter((v): v is string => v !== null);
      const objects = value.filter(
        (v): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v)
      );
      if (scalars.length === 0 && objects.length === 0) return;
      if (scalars.length > 0) {
        rows.push(
          <Text key={key} variant="caption" color="secondary">
            {label}: {scalars.join(", ")}
          </Text>
        );
      }
      objects.forEach((item, index) => {
        rows.push(
          <View key={`${key}-${index}`} className="gap-1">
            <Text variant="caption" weight="semibold">
              {label} {index + 1}
            </Text>
            <CapturedRows data={item} depth={depth + 1} />
          </View>
        );
      });
      return;
    }
    if (typeof value === "object") {
      const nested = value as Record<string, unknown>;
      if (Object.keys(nested).length === 0) return;
      rows.push(
        <View key={key} className="gap-1">
          <Text variant="caption" weight="semibold">
            {label}
          </Text>
          <CapturedRows data={nested} depth={depth + 1} />
        </View>
      );
      return;
    }
    const text = scalarText(value);
    if (text === null) return;
    rows.push(
      <Text key={key} variant="caption" color="secondary">
        {label}: {text}
      </Text>
    );
  });
  return <View className={`gap-1 ${depth > 0 ? "pl-3" : ""}`}>{rows}</View>;
}

export type LeadDetailScreenProps = {
  lead: Lead;
  onBack: () => void;
  onGenerateQuote: (lead: Lead) => void;
  onRequestSiteVisit: (lead: Lead) => void;
  onOpenChat?: (lead: Lead) => void;
  onMarkDead?: (lead: Lead) => void;
};

export function LeadDetailScreen({
  lead,
  onBack,
  onGenerateQuote,
  onRequestSiteVisit,
  onOpenChat,
  onMarkDead,
}: LeadDetailScreenProps) {
  const [dead, setDead] = useState(false);
  const { business } = useBusiness();

  // Latest AI message may carry suggested questions for the electrician's call.
  const { data: threadMessages } = useQuery({
    queryKey: ["communications", lead.id],
    queryFn: () => fetchCommunications(lead.id),
  });
  const lastAiMessage = [...(threadMessages ?? [])].reverse().find((m) => m.senderRole === "ai");
  const suggestedQuestions = (lastAiMessage?.aiMetadata?.suggestedQuestions ?? []).filter(
    (q) => typeof q === "string" && q.trim().length > 0
  );

  const capturedData = lead.structuredData ?? {};
  const hasCapturedDetails = Object.values(capturedData).some(
    (value) =>
      value != null &&
      (typeof value !== "object" || Object.keys(value as Record<string, unknown>).length > 0)
  );

  const handleCall = () => {
    if (!lead.customerPhone) return;
    void Linking.openURL(`tel:${lead.customerPhone.replace(/\s+/g, "")}`);
  };

  // Invite a lead without a customer account to the app: they sign up with the
  // same email/phone and the backend links their quotes automatically.
  const handleInvite = () => {
    const code = business?.code ?? "";
    const message =
      `Hi ${lead.customerName.split(" ")[0]}, ${business?.name ?? "your electrician"} uses ` +
      `My Trade Portal to share and track quotes. Download the app and sign up with this ` +
      `email/phone plus business code ${code} to follow your quote.`;
    if (lead.customerEmail) {
      const url =
        `mailto:${lead.customerEmail}?subject=${encodeURIComponent("Track your quote in our customer app")}` +
        `&body=${encodeURIComponent(message)}`;
      void Linking.openURL(url);
    } else if (lead.customerPhone) {
      const url = `sms:${lead.customerPhone.replace(/\s+/g, "")}?body=${encodeURIComponent(message)}`;
      void Linking.openURL(url);
    }
  };

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
            <View className="flex-row gap-1">
              {lead.requiresCallback && (
                <View testID="lead-requires-callback" className="rounded-lg bg-amber-100 px-2 py-1">
                  <Text variant="caption" color="warning">
                    CALL BACK
                  </Text>
                </View>
              )}
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
          </View>
          <Text variant="caption" color="secondary">
            {getLeadSourceLabel(lead.source)} · {lead.postcode} · {formatUrgency(lead.urgency)}
          </Text>
          <Text variant="caption" color="secondary">
            Received {formatDateUK(lead.createdAt)}
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

        {hasCapturedDetails && (
          <View testID="lead-captured-details" className="rounded-2xl bg-slate-100 p-4 gap-2">
            <Text variant="body" weight="semibold">
              Captured details
            </Text>
            <CapturedRows data={capturedData} />
          </View>
        )}

        {suggestedQuestions.length > 0 && (
          <View testID="lead-suggested-questions" className="rounded-2xl bg-indigo-50 p-4 gap-2">
            <Text variant="body" weight="semibold">
              AI-suggested questions for your call
            </Text>
            {suggestedQuestions.map((question) => (
              <Text key={question} variant="caption" color="secondary">
                • {question}
              </Text>
            ))}
          </View>
        )}

        <View className="gap-3 pt-2">
          {lead.customerPhone && (
            <Button
              testID="lead-call-customer"
              title={`Call ${lead.customerName.split(" ")[0]}`}
              variant={lead.requiresCallback ? "primary" : "outline"}
              onPress={handleCall}
            />
          )}
          <Button testID="lead-generate-quote" title="Generate AI quote" onPress={() => onGenerateQuote(lead)} />
          {onOpenChat && lead.customerId && (
            <Button
              testID="lead-open-chat"
              title="Open chat"
              variant="outline"
              onPress={() => onOpenChat(lead)}
            />
          )}
          {!lead.customerId && (lead.customerEmail || lead.customerPhone) && (
            <Button
              testID="lead-invite-to-app"
              title="Invite to app"
              variant="outline"
              onPress={handleInvite}
            />
          )}
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

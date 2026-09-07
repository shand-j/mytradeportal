import { useState } from "react";
import { Pressable, ScrollView, View } from "react-native";
import { Button } from "../../../components/ui/Button";
import { FormField } from "../../../components/ui/FormField";
import { Text } from "../../../components/ui/Text";
import { VerificationBadge } from "../../../components/ui/VerificationBadge";

type BusinessIdentityStepProps = {
  data?: Record<string, unknown>;
  onNext: (data?: Record<string, unknown>) => void;
};

const STRUCTURES = [
  { key: "sole_trader", label: "Sole trader" },
  { key: "ltd", label: "Limited company" },
  { key: "llp", label: "LLP" },
  { key: "partnership", label: "Partnership" },
];

export function BusinessIdentityStep({ data, onNext }: BusinessIdentityStepProps) {
  const [tradingName, setTradingName] = useState((data?.tradingName as string) ?? "");
  const [structure, setStructure] = useState((data?.structure as string) ?? "ltd");
  const [year, setYear] = useState((data?.year as string) ?? "");
  const [website, setWebsite] = useState((data?.website as string) ?? "");
  const [chNumber, setChNumber] = useState((data?.chNumber as string) ?? "");
  const [quotesPerWeek, setQuotesPerWeek] = useState(
    data?.quotesPerWeek != null ? String(data.quotesPerWeek) : ""
  );
  const [avgMinutesPerQuote, setAvgMinutesPerQuote] = useState(
    data?.avgMinutesPerQuote != null ? String(data.avgMinutesPerQuote) : ""
  );
  const [chStatus] = useState<"self_declared" | "verified" | "pending">(
    (data?.chStatus as "self_declared" | "verified" | "pending") ?? "self_declared"
  );

  const isLtd = structure === "ltd" || structure === "llp";

  return (
    <ScrollView className="flex-1">
      <View className="gap-4 pb-6">
        <Text variant="title" weight="bold">
          Business identity
        </Text>
        <Text variant="body" color="secondary">
          Customers see this on quotes and the App Store listing.
        </Text>

        <FormField
          label="Trading name"
          value={tradingName}
          onChangeText={setTradingName}
          placeholder="e.g. Smith Electrical Ltd"
        />

        <Text variant="body" weight="semibold">
          Business structure
        </Text>
        <View className="flex-row flex-wrap gap-2">
          {STRUCTURES.map((s) => (
            <Button
              key={s.key}
              title={s.label}
              variant={structure === s.key ? "primary" : "outline"}
              onPress={() => setStructure(s.key)}
            />
          ))}
        </View>

        {structure === "sole_trader" && (
          <View className="rounded-2xl bg-amber-50 p-4">
            <Text variant="body" weight="semibold" color="warning">
              MTD hint
            </Text>
            <Text variant="caption" color="secondary">
              From April 2026, sole traders over £50k must use MTD-compatible software — we sync with Xero/QuickBooks/FreeAgent.
            </Text>
          </View>
        )}

        {isLtd && (
          <View className="gap-3">
            <FormField
              label="Companies House number"
              value={chNumber}
              onChangeText={setChNumber}
              placeholder="12345678"
              keyboardType="number-pad"
              maxLength={8}
            />
            <Button
              title="Verify with Companies House"
              variant="outline"
              disabled={chNumber.length !== 8}
            />
            <Text variant="caption" color="secondary">
              Online Companies House verification is not yet implemented.
            </Text>
            <VerificationBadge status={chStatus} />
          </View>
        )}

        <FormField
          label="Year established"
          value={year}
          onChangeText={setYear}
          placeholder="YYYY"
          keyboardType="number-pad"
          maxLength={4}
        />

        <FormField
          label="Website / Facebook (optional)"
          value={website}
          onChangeText={setWebsite}
          placeholder="https://..."
          autoCapitalize="none"
          helper="Used to suggest a logo later."
        />

        <FormField
          label="Quotes you typically send per week"
          value={quotesPerWeek}
          onChangeText={setQuotesPerWeek}
          placeholder="e.g. 6"
          keyboardType="number-pad"
        />

        <FormField
          label="Average time per quote (minutes)"
          value={avgMinutesPerQuote}
          onChangeText={setAvgMinutesPerQuote}
          placeholder="e.g. 45"
          keyboardType="number-pad"
          helper="Used to show how much time AI quoting saves you."
        />

        <Button
          title="Continue"
          onPress={() =>
            onNext({
              tradingName,
              structure,
              year,
              website,
              chNumber,
              chStatus,
              quotesPerWeek: quotesPerWeek.trim() ? parseInt(quotesPerWeek, 10) || undefined : undefined,
              avgMinutesPerQuote: avgMinutesPerQuote.trim()
                ? parseInt(avgMinutesPerQuote, 10) || undefined
                : undefined,
            })
          }
          disabled={!tradingName}
        />
      </View>
    </ScrollView>
  );
}

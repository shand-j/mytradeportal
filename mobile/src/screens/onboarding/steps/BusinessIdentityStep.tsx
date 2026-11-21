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
  const [yearError, setYearError] = useState<string | null>(null);
  const [websiteError, setWebsiteError] = useState<string | null>(null);
  const [quotesError, setQuotesError] = useState<string | null>(null);
  const [minutesError, setMinutesError] = useState<string | null>(null);

  const isLtd = structure === "ltd" || structure === "llp";
  const currentYear = new Date().getFullYear();

  const validateUrl = (raw: string): string | null => {
    const value = raw.trim();
    if (!value) return null;
    try {
      const parsed = new URL(value);
      if (!/^https?:$/.test(parsed.protocol) || !parsed.hostname.includes(".")) {
        return "Enter a full http:// or https:// website address.";
      }
      return null;
    } catch {
      return "Enter a full http:// or https:// website address.";
    }
  };

  const validateAndContinue = () => {
    const nextYearError = (() => {
      const value = year.trim();
      if (!value) return null;
      if (!/^\d{4}$/.test(value)) return "Enter a valid four-digit year.";
      const numeric = Number(value);
      if (numeric < 1800 || numeric > currentYear) {
        return `Enter a year between 1800 and ${currentYear}.`;
      }
      return null;
    })();
    const nextWebsiteError = validateUrl(website);
    const nextQuotesError = (() => {
      const value = quotesPerWeek.trim();
      if (!value) return null;
      const numeric = Number(value);
      if (!Number.isInteger(numeric) || numeric < 0) {
        return "Enter zero or a positive whole number.";
      }
      return null;
    })();
    const nextMinutesError = (() => {
      const value = avgMinutesPerQuote.trim();
      if (!value) return null;
      const numeric = Number(value);
      if (!Number.isInteger(numeric) || numeric < 0) {
        return "Enter zero or a positive whole number.";
      }
      return null;
    })();

    setYearError(nextYearError);
    setWebsiteError(nextWebsiteError);
    setQuotesError(nextQuotesError);
    setMinutesError(nextMinutesError);
    if (nextYearError || nextWebsiteError || nextQuotesError || nextMinutesError) return;

    onNext({
      tradingName,
      structure,
      year: year.trim() || undefined,
      website: website.trim() || undefined,
      chNumber,
      chStatus,
      quotesPerWeek: quotesPerWeek.trim() ? parseInt(quotesPerWeek, 10) : undefined,
      avgMinutesPerQuote: avgMinutesPerQuote.trim()
        ? parseInt(avgMinutesPerQuote, 10)
        : undefined,
    });
  };

  return (
    <ScrollView className="flex-1" keyboardShouldPersistTaps="handled">
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
            <VerificationBadge status={chStatus} />
          </View>
        )}

        <FormField
          label="Year established"
          value={year}
          onChangeText={(value) => {
            setYear(value);
            setYearError(null);
          }}
          placeholder="YYYY"
          keyboardType="number-pad"
          maxLength={4}
          error={yearError}
        />

        <FormField
          label="Website / Facebook (optional)"
          value={website}
          onChangeText={(value) => {
            setWebsite(value);
            setWebsiteError(null);
          }}
          placeholder="https://..."
          autoCapitalize="none"
          helper="Used to suggest a logo later."
          error={websiteError}
        />

        <FormField
          label="Quotes you typically send per week"
          value={quotesPerWeek}
          onChangeText={(value) => {
            setQuotesPerWeek(value);
            setQuotesError(null);
          }}
          placeholder="e.g. 6"
          keyboardType="number-pad"
          error={quotesError}
        />

        <FormField
          label="Average time per quote (minutes)"
          value={avgMinutesPerQuote}
          onChangeText={(value) => {
            setAvgMinutesPerQuote(value);
            setMinutesError(null);
          }}
          placeholder="e.g. 45"
          keyboardType="number-pad"
          helper="Used to show how much time AI quoting saves you."
          error={minutesError}
        />

        <Button
          title="Continue"
          onPress={validateAndContinue}
          disabled={!tradingName}
        />
      </View>
    </ScrollView>
  );
}

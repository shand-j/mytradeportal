import { useState } from "react";
import { Pressable, ScrollView, View } from "react-native";
import { Button } from "../../../components/ui/Button";
import { FormField } from "../../../components/ui/FormField";
import { Text } from "../../../components/ui/Text";

type BrandingStepProps = {
  data?: Record<string, unknown>;
  onNext: (data?: Record<string, unknown>) => void;
};

/** Preset brand colours offered during onboarding (hex). */
const BRAND_COLOURS = [
  "#FFC107", // hi-vis yellow
  "#0EA5E9", // sky
  "#059669", // emerald
  "#D97706", // amber
  "#DC2626", // red
  "#111827", // slate
];

const HEX_RE = /^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/;

/** Soft check: review links should be full https URLs, but never block the step. */
function reviewUrlWarning(raw: string): string | null {
  const value = raw.trim();
  if (!value) return null;
  return /^https:\/\/.+\..+/.test(value)
    ? null
    : "This doesn't look like a full https:// link — customers will be sent here exactly as typed.";
}

/** Normalise #RGB/#RRGGBB (any case, # optional) to uppercase #RRGGBB, or null. */
function normaliseHex(raw: string): string | null {
  const match = raw.trim().match(HEX_RE);
  if (!match) return null;
  let digits = match[1];
  if (digits.length === 3) {
    digits = digits
      .split("")
      .map((c) => c + c)
      .join("");
  }
  return `#${digits.toUpperCase()}`;
}

export function BrandingStep({ data, onNext }: BrandingStepProps) {
  const [primaryColor, setPrimaryColor] = useState(
    (data?.primaryColor as string) ?? BRAND_COLOURS[0]
  );
  const [hexInput, setHexInput] = useState(primaryColor.toUpperCase());
  const [hexError, setHexError] = useState<string | null>(null);
  const [reviewUrl, setReviewUrl] = useState((data?.reviewUrl as string) ?? "");

  const pickPreset = (colour: string) => {
    setPrimaryColor(colour);
    setHexInput(colour.toUpperCase());
    setHexError(null);
  };

  const onHexChange = (raw: string) => {
    setHexInput(raw);
    const hex = normaliseHex(raw);
    if (hex) {
      setPrimaryColor(hex);
      setHexError(null);
    } else if (raw.trim().length > 0) {
      setHexError("Enter a valid hex colour, e.g. #FFC107");
    } else {
      setHexError(null);
    }
  };

  return (
    <ScrollView className="flex-1" keyboardShouldPersistTaps="handled">
      <View className="gap-4 pb-6">
        <Text variant="title" weight="bold">
          Branding
        </Text>
        <Text variant="body" color="secondary">
          Brand colour, email blurb, and quote PDF template. These make the customer portal look like your business.
        </Text>

        <View className="rounded-2xl bg-slate-100 p-4 gap-3">
          <Text variant="body" weight="semibold">
            Brand colour
          </Text>
          <Text variant="caption" color="secondary">
            Pick a preset or type your own hex code. Used across your customer app, quotes, and emails — changeable later in Settings.
          </Text>
          <View className="flex-row flex-wrap gap-3">
            {BRAND_COLOURS.map((colour) => {
              const selected = primaryColor === colour;
              return (
                <Pressable
                  key={colour}
                  testID={`brand-colour-${colour.slice(1).toLowerCase()}`}
                  onPress={() => pickPreset(colour)}
                  accessibilityLabel={`Brand colour ${colour}`}
                >
                  <View
                    className={`h-10 w-10 rounded-full ${selected ? "border-2 border-slate-900" : ""}`}
                    style={{ backgroundColor: colour }}
                  />
                </Pressable>
              );
            })}
          </View>
          <View className="flex-row items-center gap-3">
            <View
              testID="brand-colour-preview"
              className="h-10 w-10 rounded-full border border-slate-300"
              style={{ backgroundColor: primaryColor }}
            />
            <View className="flex-1">
              <FormField
                label="Custom hex colour"
                value={hexInput}
                onChangeText={onHexChange}
                placeholder="#FFC107"
                autoCapitalize="characters"
                error={hexError}
              />
            </View>
          </View>
        </View>

        <View className="rounded-2xl bg-slate-100 p-4 gap-3">
          <FormField
            testID="branding-review-url"
            label="Review link (Google, Checkatrade, Trustpilot…)"
            value={reviewUrl}
            onChangeText={setReviewUrl}
            placeholder="https://g.page/r/your-business/review"
            autoCapitalize="none"
            keyboardType="default"
            helper="We'll ask your customers for a review after they pay."
          />
          {reviewUrlWarning(reviewUrl) && (
            <Text testID="branding-review-url-warning" variant="caption" color="warning">
              {reviewUrlWarning(reviewUrl)}
            </Text>
          )}
        </View>

        <Button
          testID="branding-continue"
          title="Continue"
          onPress={() => onNext({ primaryColor, reviewUrl: reviewUrl.trim() || undefined })}
        />
        <Button title="Skip for now" variant="outline" onPress={() => onNext({ skipped: true })} />
      </View>
    </ScrollView>
  );
}

import { useState } from "react";
import { Pressable, ScrollView, View } from "react-native";
import { Button } from "../../../components/ui/Button";
import { FileUploadPlaceholder } from "../../../components/ui/FileUploadPlaceholder";
import { Text } from "../../../components/ui/Text";

type BrandingStepProps = {
  data?: Record<string, unknown>;
  onNext: (data?: Record<string, unknown>) => void;
};

/** Preset brand colours offered during onboarding (hex). */
const BRAND_COLOURS = [
  "#2563EB", // blue
  "#0EA5E9", // sky
  "#4F46E5", // indigo
  "#059669", // emerald
  "#D97706", // amber
  "#DC2626", // red
  "#DB2777", // pink
  "#111827", // slate
];

export function BrandingStep({ data, onNext }: BrandingStepProps) {
  const [primaryColor, setPrimaryColor] = useState(
    (data?.primaryColor as string) ?? BRAND_COLOURS[0]
  );

  return (
    <ScrollView className="flex-1">
      <View className="gap-4 pb-6">
        <Text variant="title" weight="bold">
          Branding
        </Text>
        <Text variant="body" color="secondary">
          Logo, brand colour, email blurb, and quote PDF template. These make the customer portal look like your business.
        </Text>

        <FileUploadPlaceholder label="Upload logo" />

        <View className="rounded-2xl bg-slate-100 p-4 gap-3">
          <Text variant="body" weight="semibold">
            Brand colour
          </Text>
          <Text variant="caption" color="secondary">
            Used across your customer app, quotes, and emails. You can change it from Settings later.
          </Text>
          <View className="flex-row flex-wrap gap-3">
            {BRAND_COLOURS.map((colour) => {
              const selected = primaryColor === colour;
              return (
                <Pressable
                  key={colour}
                  testID={`brand-colour-${colour.slice(1).toLowerCase()}`}
                  onPress={() => setPrimaryColor(colour)}
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
              className="h-12 flex-1 rounded-xl"
              style={{ backgroundColor: primaryColor }}
            />
            <Text variant="body" weight="semibold">
              {primaryColor.toUpperCase()}
            </Text>
          </View>
        </View>

        <Button
          testID="branding-continue"
          title="Continue"
          onPress={() => onNext({ primaryColor })}
        />
        <Button title="Skip for now" variant="outline" onPress={() => onNext({ skipped: true })} />
      </View>
    </ScrollView>
  );
}

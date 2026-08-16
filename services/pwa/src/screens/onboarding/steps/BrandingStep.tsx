import { ScrollView, View } from "react-native";
import { Button } from "../../../components/ui/Button";
import { FileUploadMock } from "../../../components/ui/FileUploadMock";
import { Text } from "../../../components/ui/Text";

type BrandingStepProps = {
  data?: Record<string, unknown>;
  onNext: (data?: Record<string, unknown>) => void;
};

export function BrandingStep({ onNext }: BrandingStepProps) {
  return (
    <ScrollView className="flex-1">
      <View className="gap-4 pb-6">
        <Text variant="title" weight="bold">
          Branding
        </Text>
        <Text variant="body" color="secondary">
          Logo, brand colour, email blurb, and quote PDF template. These make the customer portal look like your business.
        </Text>

        <FileUploadMock label="Upload logo" fileName="logo.png" />

        <View className="rounded-2xl bg-slate-100 p-4">
          <Text variant="body" weight="semibold">
            Default brand colour
          </Text>
          <Text variant="caption" color="secondary">
            Demo blue (#2563EB) is applied. You can change it from Settings later.
          </Text>
        </View>

        <Button title="Skip for now" variant="outline" onPress={() => onNext({ skipped: true })} />
      </View>
    </ScrollView>
  );
}

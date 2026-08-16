import { useState } from "react";
import { ScrollView, View } from "react-native";
import { Button } from "../../components/ui/Button";
import { FileUploadMock } from "../../components/ui/FileUploadMock";
import { FormField } from "../../components/ui/FormField";
import { Header } from "../../components/ui/Header";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { useBusiness } from "../../theme/ThemeProvider";

export type BrandingSettingsScreenProps = {
  onClose: () => void;
};

export function BrandingSettingsScreen({ onClose }: BrandingSettingsScreenProps) {
  const { business, setBusiness } = useBusiness();
  const [name, setName] = useState(business?.name ?? "");
  const [phone, setPhone] = useState(business?.contactPhone ?? "");
  const [address, setAddress] = useState(business?.address ?? "");

  const save = () => {
    if (business) {
      setBusiness({ ...business, name: name || business.name, contactPhone: phone, address });
    }
    onClose();
  };

  return (
    <Screen>
      <Header testID="branding-back" title="Branding" onBack={onClose} />

      <ScrollView className="flex-1" contentContainerClassName="gap-4 pb-4">
        <View className="rounded-2xl bg-slate-100 p-4 gap-3">
          <FormField label="Business name" value={name} onChangeText={setName} placeholder="Business name" />
          <FormField
            label="Contact phone"
            value={phone}
            onChangeText={setPhone}
            placeholder="Phone"
            keyboardType="phone-pad"
          />
          <FormField label="Address" value={address} onChangeText={setAddress} placeholder="Address" />
        </View>

        <View className="rounded-2xl bg-slate-100 p-4 gap-3">
          <Text variant="body" weight="semibold">
            Logo
          </Text>
          <FileUploadMock label="Upload logo" fileName="logo.png" testID="branding-logo-upload" />
        </View>

        <View className="rounded-2xl bg-slate-100 p-4 gap-3">
          <Text variant="body" weight="semibold">
            Primary colour
          </Text>
          <Text variant="caption" color="secondary">
            White-label colour preview:
          </Text>
          <View className="h-12 rounded-xl" style={{ backgroundColor: business?.primaryColor ?? "#2563EB" }} />
        </View>

        <View className="rounded-2xl bg-slate-100 p-4 gap-3">
          <Text variant="body" weight="semibold">
            Quote PDF template
          </Text>
          <FileUploadMock label="Upload PDF template" fileName="quote-template.pdf" />
        </View>
      </ScrollView>

      <View className="border-t border-slate-200 bg-white pt-4 pb-2 gap-3">
        <Button title="Save branding" onPress={save} />
      </View>
    </Screen>
  );
}

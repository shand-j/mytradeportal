import { ScrollView, View } from "react-native";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { Icon } from "../../components/ui/Icon";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";

export type CertificatesScreenProps = {
  onBack: () => void;
  onOpen: (id: string) => void;
  onNew: () => void;
};

export function CertificatesScreen({ onBack, onNew }: CertificatesScreenProps) {
  return (
    <Screen>
      <Header title="Certificates" onBack={onBack} />

      <ScrollView className="flex-1" contentContainerStyle={{ gap: 16, paddingBottom: 32 }}>
        <View className="flex-row items-center gap-3 rounded-2xl border border-primary-200 bg-primary-50 p-4">
          <View className="h-10 w-10 items-center justify-center rounded-full bg-primary">
            <Icon name="shield" size={20} color="#FFC107" />
          </View>
          <View style={{ flex: 1 }}>
            <Text variant="body" weight="semibold">
              Digital EICR certificates
            </Text>
            <Text variant="caption" color="secondary">
              Record the schedule of test results and validate Zs, RCD and IR against BS 7671.
            </Text>
          </View>
        </View>

        <Button testID="cert-new" title="New EICR" onPress={onNew} />

        <Text variant="body" weight="semibold">
          Recent certificates
        </Text>

        <View className="gap-3 rounded-2xl bg-gray-100 p-6">
          <Text variant="body" align="center" color="secondary">
            No certificates yet
          </Text>
          <Text variant="caption" align="center" color="secondary">
            Certificates you issue will appear here.
          </Text>
        </View>
      </ScrollView>
    </Screen>
  );
}

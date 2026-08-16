import { Pressable, ScrollView, View } from "react-native";
import { useRouter } from "expo-router";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { Icon } from "../../components/ui/Icon";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { MOCK_CERTIFICATES } from "../../data/mockCertificates";

export type CertificatesScreenProps = {
  onBack: () => void;
  onOpen: (id: string) => void;
  onNew: () => void;
};

export function CertificatesScreen({ onBack, onOpen, onNew }: CertificatesScreenProps) {
  return (
    <Screen>
      <Header title="Certificates" onBack={onBack} />

      <ScrollView className="flex-1" contentContainerStyle={{ gap: 16, paddingBottom: 32 }}>
        <View className="flex-row items-center gap-3 rounded-2xl border border-indigo-100 bg-indigo-50 p-4">
          <View className="h-10 w-10 items-center justify-center rounded-full bg-indigo-600">
            <Icon name="mic" size={20} color="#FFFFFF" />
          </View>
          <View style={{ flex: 1 }}>
            <Text variant="body" weight="semibold">
              Voice-to-certificate
            </Text>
            <Text variant="caption" color="secondary">
              Dictate an EICR on site — the AI fills the schedule and validates BS 7671.
            </Text>
          </View>
        </View>

        <Button testID="cert-new" title="New EICR (voice)" onPress={onNew} />

        <Text variant="body" weight="semibold">
          Recent certificates
        </Text>

        {MOCK_CERTIFICATES.map((cert) => {
          const ok = cert.overall === "satisfactory";
          return (
            <Pressable key={cert.id} testID={`cert-card-${cert.id}`} onPress={() => onOpen(cert.id)}>
              <View className="gap-2 rounded-2xl border border-slate-200 bg-white p-4">
                <View className="flex-row items-center justify-between">
                  <Text variant="body" weight="semibold">
                    {cert.type} · {cert.customerName}
                  </Text>
                  <View
                    className="flex-row items-center gap-1 rounded-md px-2 py-1"
                    style={{ backgroundColor: ok ? "#ECFDF5" : "#FEF2F2" }}
                  >
                    <Icon
                      name={ok ? "circle-check" : "warning"}
                      size={13}
                      color={ok ? "#16A34A" : "#DC2626"}
                    />
                    <Text
                      variant="caption"
                      weight="semibold"
                      style={{ color: ok ? "#16A34A" : "#DC2626", fontSize: 11 }}
                    >
                      {ok ? "SATISFACTORY" : "UNSATISFACTORY"}
                    </Text>
                  </View>
                </View>
                <Text variant="caption" color="secondary">
                  {cert.postcode} · {cert.circuits.length} circuits ·{" "}
                  {new Date(cert.createdAt).toLocaleDateString()}
                </Text>
              </View>
            </Pressable>
          );
        })}
      </ScrollView>
    </Screen>
  );
}

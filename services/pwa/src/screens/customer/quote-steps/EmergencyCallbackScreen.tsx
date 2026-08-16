import { Linking, StyleSheet, View } from "react-native";
import { Button } from "../../../components/ui/Button";
import { Icon } from "../../../components/ui/Icon";
import { Text } from "../../../components/ui/Text";
import { useBusiness } from "../../../theme/ThemeProvider";
import { StepPropsWithBusiness, TriageLevel } from "./types";

type EmergencyCallbackScreenProps = StepPropsWithBusiness & {
  triage: TriageLevel;
  onDone: () => void;
};

export function EmergencyCallbackScreen({ onDone, onBack }: EmergencyCallbackScreenProps) {
  const { business } = useBusiness();
  const phone = business?.contactPhone?.replace(/\s/g, "") ?? "";
  const businessName = business?.name ?? "your electrician";

  const openDialer = () => {
    if (phone) Linking.openURL(`tel:${phone}`).catch(() => {});
  };

  const openSms = () => {
    if (phone) Linking.openURL(`sms:${phone}`).catch(() => {});
  };

  const openWhatsApp = () => {
    Linking.openURL("whatsapp://").catch(() => {
      // If WhatsApp is not installed, fallback silently in mock
    });
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Icon name="warning" size={40} color="#FFFFFF" />
        <Text variant="title" weight="bold" align="center" style={styles.headerText}>
          Electrical emergency
        </Text>
        <Text variant="body" align="center" style={styles.headerText}>
          Call {businessName} now
        </Text>
      </View>

      <View style={styles.card}>
        <Text variant="body" color="secondary">
          If you can do so safely, switch off the power at the main switch and stay away from the
          affected area.
        </Text>

        <Text variant="body" weight="semibold">
          Safety guidance
        </Text>
        <View style={styles.bulletList}>
          <Text variant="caption" color="secondary">
            • Do not touch electrical equipment that is wet or sparking.
          </Text>
          <Text variant="caption" color="secondary">
            • If you smell burning or see smoke, leave the property and call from outside.
          </Text>
          <Text variant="caption" color="secondary">
            • In immediate danger, call 999 first.
          </Text>
        </View>
      </View>

      <Button
        testID="quote-emergency-call"
        title={phone ? `Call ${business?.contactPhone}` : "Call now"}
        variant="primary"
        onPress={openDialer}
      />

      <View style={styles.fallbacks}>
        <Button testID="quote-emergency-sms" title="Send SMS" variant="outline" onPress={openSms} />
        <Button
          testID="quote-emergency-whatsapp"
          title="Open WhatsApp"
          variant="outline"
          onPress={openWhatsApp}
        />
      </View>

      <Button testID="quote-emergency-done" title="I’ve called - finish" variant="ghost" onPress={onDone} />

      <Button title="Back" variant="ghost" onPress={onBack} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: 16,
  },
  header: {
    alignItems: "center",
    gap: 8,
    padding: 24,
    borderRadius: 16,
    backgroundColor: "#EF4444",
  },
  headerText: {
    color: "#FFFFFF",
  },
  card: {
    gap: 12,
    padding: 16,
    borderRadius: 16,
    backgroundColor: "#FEF2F2",
    borderWidth: 1,
    borderColor: "#FECACA",
  },
  bulletList: {
    gap: 6,
  },
  fallbacks: {
    flexDirection: "row",
    gap: 12,
  },
});

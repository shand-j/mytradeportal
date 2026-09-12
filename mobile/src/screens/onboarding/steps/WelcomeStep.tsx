import { StyleSheet, View } from "react-native";
import { Button } from "../../../components/ui/Button";
import { Text } from "../../../components/ui/Text";
import { useAuth } from "../../../contexts/AuthContext";
import { useBusiness } from "../../../theme/ThemeProvider";

type WelcomeStepProps = {
  data?: Record<string, unknown>;
  onNext: (data?: Record<string, unknown>) => void;
};

const VALUE_PROPS = [
  "Get leads from QR codes, WhatsApp, and your website.",
  "AI drafts quotes; you review and send in seconds.",
  "Certificates, invoices, and accounts in one place.",
];

const LAUNCH_PREVIEW_STEPS = [
  "Account",
  "Business",
  "Address",
  "Tax",
  "Compliance",
  "Services",
];

export function WelcomeStep({ onNext }: WelcomeStepProps) {
  const { business } = useBusiness();
  const { logout } = useAuth();

  return (
    <View style={styles.container}>
      <Text variant="title" weight="bold" align="center">
        Run your electrical business from your phone.
      </Text>

      <View style={styles.valueProps}>
        {VALUE_PROPS.map((text) => (
          <Text key={text} variant="body" color="secondary">
            • {text}
          </Text>
        ))}
      </View>

      <View style={styles.preview}>
        <Text variant="caption" weight="semibold" color="secondary" align="center">
          6-step launch preview
        </Text>
        <View style={styles.dots}>
          {LAUNCH_PREVIEW_STEPS.map((step, index) => (
            <View key={step} style={styles.step}>
              <View style={styles.dot} />
              <Text variant="caption" color="secondary" align="center">
                {step}
              </Text>
            </View>
          ))}
          <View style={styles.step}>
            <View style={[styles.dot, styles.launchDot]} />
            <Text variant="caption" color="success" align="center">
              Launch
            </Text>
          </View>
        </View>
      </View>

      <Button title="Create my account" onPress={() => onNext({ onboarding_started: true })} />
      <Button title="I already have an account" variant="ghost" onPress={logout} />

      {business?.name ? (
        <Text variant="caption" color="secondary" align="center">
          Setting up {business.name}
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: 16,
  },
  valueProps: {
    gap: 8,
    marginTop: 8,
  },
  preview: {
    gap: 12,
    paddingVertical: 16,
  },
  dots: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-start",
    gap: 8,
  },
  step: {
    flex: 1,
    alignItems: "center",
    gap: 6,
  },
  dot: {
    width: 16,
    height: 16,
    borderRadius: 8,
    backgroundColor: "#C3CFD5",
  },
  launchDot: {
    backgroundColor: "#FFC107",
  },
});

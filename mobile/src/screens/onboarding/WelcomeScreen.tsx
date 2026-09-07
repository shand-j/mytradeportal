import { StyleSheet, View } from "react-native";
import { Button } from "../../components/ui/Button";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { useAuth } from "../../contexts/AuthContext";
import { useBusiness } from "../../theme/ThemeProvider";
import { useRouter } from "expo-router";

const LAUNCH_STEPS = [
  "Business identity",
  "Compliance & credentials",
  "Services offered",
  "Pricing setup",
  "Branding",
  "Review & launch",
];

export function WelcomeScreen() {
  const { startRegistration } = useAuth();
  const { business } = useBusiness();
  const router = useRouter();

  const startOnboarding = () => {
    startRegistration("trade");
    router.push("/onboarding");
  };

  const businessName = business?.name ?? "My Trade Portal";

  return (
    <Screen style={styles.container}>
      <Text variant="title" weight="bold" align="center">
        {businessName}
      </Text>
      <Text variant="subtitle" color="secondary" align="center">
        Get leads. Send quotes. Stay compliant.
      </Text>

      <View style={styles.valueProps}>
        <Text variant="body" color="secondary">
          • Turn WhatsApp messages into draft quotes
        </Text>
        <Text variant="body" color="secondary">
          • Send AI-assisted quotes in minutes
        </Text>
        <Text variant="body" color="secondary">
          • Calendar, navigation and job assignments in one app
        </Text>
      </View>

      <View style={styles.stepsCard}>
        <Text variant="body" weight="semibold">
          6 launch steps
        </Text>
        {LAUNCH_STEPS.map((step, index) => (
          <Text key={step} variant="caption" color="secondary">
            {index + 1}. {step}
          </Text>
        ))}
      </View>

      <View style={styles.spacer} />
      <Button title="Create my account" onPress={startOnboarding} />
      <Button title="I already have an account" variant="outline" onPress={() => router.push("/trade-login")} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    paddingVertical: 24,
    justifyContent: "center",
    gap: 16,
  },
  valueProps: {
    gap: 8,
    marginTop: 8,
  },
  stepsCard: {
    padding: 16,
    borderRadius: 16,
    backgroundColor: "#F3F4F6",
    gap: 8,
  },
  spacer: {
    height: 32,
  },
});

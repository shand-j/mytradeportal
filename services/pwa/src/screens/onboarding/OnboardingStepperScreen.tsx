import { useState } from "react";
import { ScrollView, StyleSheet, View } from "react-native";
import { Header } from "../../components/ui/Header";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { useAuth } from "../../contexts/AuthContext";
import { useBusiness } from "../../theme/ThemeProvider";
import { AccountStep } from "./steps/AccountStep";
import { AddressServiceAreaStep } from "./steps/AddressServiceAreaStep";
import { BusinessIdentityStep } from "./steps/BusinessIdentityStep";
import { ComplianceStep } from "./steps/ComplianceStep";
import { ReviewLaunchStep } from "./steps/ReviewLaunchStep";
import { ServicesStep } from "./steps/ServicesStep";
import { TaxVatStep } from "./steps/TaxVatStep";
import { WelcomeStep } from "./steps/WelcomeStep";

const STEPS = [
  { key: "welcome", label: "Welcome", component: WelcomeStep },
  { key: "account", label: "Account", component: AccountStep },
  { key: "identity", label: "Identity", component: BusinessIdentityStep },
  { key: "address", label: "Address", component: AddressServiceAreaStep },
  { key: "tax", label: "Tax", component: TaxVatStep },
  { key: "compliance", label: "Compliance", component: ComplianceStep },
  { key: "services", label: "Services", component: ServicesStep },
  { key: "review", label: "Review", component: ReviewLaunchStep },
];

export function OnboardingStepperScreen() {
  const { business } = useBusiness();
  const { completeOnboarding, resetDemo } = useAuth();
  const [stepIndex, setStepIndex] = useState(0);
  const [data, setData] = useState<Record<string, unknown>>({});

  const StepComponent = STEPS[stepIndex].component;
  const isFirst = stepIndex === 0;
  const isLast = stepIndex === STEPS.length - 1;

  const goNext = (stepData?: Record<string, unknown>) => {
    if (stepData) {
      setData((prev) => ({ ...prev, [STEPS[stepIndex].key]: stepData }));
    }
    if (isLast) {
      completeOnboarding();
    } else {
      setStepIndex((i) => i + 1);
    }
  };

  const goBack = () => {
    if (isFirst) {
      resetDemo();
    } else {
      setStepIndex((i) => Math.max(0, i - 1));
    }
  };

  return (
    <Screen>
      <Header
        title={business?.name ?? "Onboarding"}
        onBack={isFirst ? resetDemo : goBack}
      />

      <View style={styles.progress}>
        {STEPS.map((step, index) => (
          <View
            key={step.key}
            style={[
              styles.dot,
              index <= stepIndex && styles.dotActive,
              index < stepIndex && styles.dotCompleted,
            ]}
          />
        ))}
      </View>

      <Text variant="caption" color="secondary">
        Step {stepIndex + 1} of {STEPS.length}: {STEPS[stepIndex].label}
      </Text>

      <ScrollView style={styles.scroll} contentContainerStyle={styles.content}>
        <StepComponent data={data[STEPS[stepIndex].key] as Record<string, unknown>} onNext={goNext} />
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  progress: {
    flexDirection: "row",
    gap: 8,
    marginBottom: 24,
  },
  dot: {
    flex: 1,
    height: 6,
    borderRadius: 3,
    backgroundColor: "#E5E7EB",
  },
  dotActive: {
    backgroundColor: "#2563EB",
  },
  dotCompleted: {
    opacity: 0.6,
  },
  scroll: {
    flex: 1,
  },
  content: {
    gap: 16,
    paddingBottom: 24,
  },
});

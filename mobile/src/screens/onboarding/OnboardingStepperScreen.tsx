import { useEffect, useRef, useState } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Header } from "../../components/ui/Header";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { useAuth } from "../../contexts/AuthContext";
import { useBusiness } from "../../theme/ThemeProvider";
import { ApiError } from "../../lib/apiClient";
import {
  RegisterBusinessInput,
  completeOnboardingSteps,
  getOnboardingStatus,
} from "../../api/onboarding";
import { AccountStep } from "./steps/AccountStep";
import { AddressServiceAreaStep } from "./steps/AddressServiceAreaStep";
import { BankDetailsStep } from "./steps/BankDetailsStep";
import { BrandingStep } from "./steps/BrandingStep";
import { BusinessIdentityStep } from "./steps/BusinessIdentityStep";
import { CardPaymentsStep } from "./steps/CardPaymentsStep";
import { ComplianceStep } from "./steps/ComplianceStep";
import { PlanPaymentStep } from "./steps/PlanPaymentStep";
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
  { key: "branding", label: "Branding", component: BrandingStep },
  { key: "review", label: "Review", component: ReviewLaunchStep },
  // Post-registration steps: the tenant exists from the review step, so bank
  // details (always) and the card-payments gate save straight to it (#188/189).
  { key: "bank_details", label: "Bank details", component: BankDetailsStep },
  { key: "card_payments", label: "Card payments", component: CardPaymentsStep },
  { key: "plan", label: "Plan", component: PlanPaymentStep },
];

/** Map the collected wizard data into the shape the backend needs to provision. */
function buildRegisterInput(data: Record<string, unknown>): RegisterBusinessInput | null {
  const account = (data.account ?? {}) as Record<string, unknown>;
  const identity = (data.identity ?? {}) as Record<string, unknown>;
  const compliance = (data.compliance ?? {}) as Record<string, unknown>;
  const services = (data.services ?? {}) as Record<string, unknown>;
  const branding = (data.branding ?? {}) as Record<string, unknown>;
  const address = (data.address ?? {}) as Record<string, unknown>;

  const email = account.email as string | undefined;
  const password = account.password as string | undefined;
  const fullName = account.fullName as string | undefined;
  if (!email || !password || !fullName) return null;

  return {
    fullName,
    email,
    password,
    phone: account.phone as string | undefined,
    role: account.role as string | undefined,
    tradingName: (identity.tradingName as string | undefined) ?? "My Electrical Business",
    address: (address.address as string | undefined) ?? undefined,
    postcode: (address.postcode as string | undefined) ?? undefined,
    tax: data.tax as Record<string, unknown> | undefined,
    identity,
    compliance,
    services: (services.services as string[] | undefined) ?? [],
    branding: branding.skipped ? undefined : branding,
  };
}

export function OnboardingStepperScreen() {
  const { business } = useBusiness();
  const { logout, finishRegistration, loading } = useAuth();
  const router = useRouter();
  const { resume } = useLocalSearchParams<{ resume?: string }>();
  // Resume mode: user logged back in with a tenant that never finished
  // onboarding. The tenant already exists, so skip straight to the review
  // step and re-record the server-side steps instead of re-registering.
  const isResume = resume === "1";
  const [stepIndex, setStepIndex] = useState(() =>
    isResume ? STEPS.findIndex((s) => s.key === "review") : 0
  );
  const [data, setData] = useState<Record<string, unknown>>({});
  const [error, setError] = useState<string | null>(null);
  // The tenant is registered when leaving the review step, so the plan step's
  // Paddle checkout call (/billing/checkout) runs with an authenticated tenant.
  const [registered, setRegistered] = useState(isResume);
  const scrollRef = useRef<ScrollView>(null);

  // Prefill the wizard from the server-side onboarding progress so the review
  // summary (and any back-navigation) shows what was already captured.
  useEffect(() => {
    if (!isResume) return;
    void (async () => {
      try {
        const status = await getOnboardingStatus();
        const progress = status.onboardingProgress ?? {};
        const keyMap: Record<string, string> = {
          business_identity: "identity",
          compliance: "compliance",
          services: "services",
          branding: "branding",
          plan: "plan",
        };
        const prefill: Record<string, unknown> = {};
        for (const [backendKey, wizardKey] of Object.entries(keyMap)) {
          const entry = progress[backendKey];
          if (entry?.value) prefill[wizardKey] = entry.value;
        }
        if (Object.keys(prefill).length > 0) {
          setData((prev) => ({ ...prefill, ...prev }));
        }
      } catch {
        // Prefill is best-effort; the wizard works from empty data too.
      }
    })();
  }, [isResume]);

  // Step transitions must reset scroll — the outer ScrollView is the actual
  // scroller (inner step ScrollViews size to content), and remounting the step
  // alone doesn't reset it.
  useEffect(() => {
    scrollRef.current?.scrollTo({ y: 0, animated: false });
  }, [stepIndex]);

  const StepComponent = STEPS[stepIndex].component;
  const isFirst = stepIndex === 0;
  const isLast = stepIndex === STEPS.length - 1;

  const goNext = async (stepData?: Record<string, unknown>) => {
    const merged = stepData ? { ...data, [STEPS[stepIndex].key]: stepData } : data;
    if (stepData) {
      setData(merged);
    }
    if (STEPS[stepIndex].key === "review") {
      setError(null);
      try {
        if (!registered) {
          await finishRegistration(buildRegisterInput(merged));
        } else if (isResume) {
          await completeOnboardingSteps(merged);
        }
        setRegistered(true);
      } catch (err) {
        const message =
          err instanceof ApiError && err.status === 409
            ? `${err.detail} Log in from the home screen instead — onboarding will resume where you left off.`
            : err instanceof ApiError
              ? err.detail
              : err instanceof Error
                ? err.message
                : "We couldn't create your business account. Please try again.";
        setError(message);
        return;
      }
    }
    if (isLast) {
      // Already registered at the review step; plan checkout opened by the step.
      router.replace("/(trade)/dashboard");
    } else {
      setStepIndex((i) => i + 1);
    }
  };

  const goBack = () => {
    if (isFirst) {
      logout();
      router.replace("/");
    } else {
      setStepIndex((i) => Math.max(0, i - 1));
    }
  };

  return (
    <Screen>
      <Header title={business?.name ?? "Onboarding"} onBack={goBack} />

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

      {error && (
        <View style={styles.errorBanner}>
          <Text variant="caption" color="warning">
            {error}
          </Text>
        </View>
      )}

      {loading && (
        <Text testID="onboarding-provisioning" variant="caption" color="secondary">
          Creating your business account…
        </Text>
      )}

      <KeyboardAvoidingView
        style={styles.keyboardAvoider}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <ScrollView
          ref={scrollRef}
          style={styles.scroll}
          contentContainerStyle={styles.content}
          keyboardShouldPersistTaps="handled"
        >
          <StepComponent
            key={stepIndex}
            // Steps normally receive only their own slice of the wizard state.
            // ReviewLaunchStep is the exception: it summarises earlier steps,
            // so it needs the root state (compliance/services/etc.).
            data={
              (STEPS[stepIndex].key === "review"
                ? data
                : data[STEPS[stepIndex].key]) as Record<string, unknown>
            }
            onNext={(stepData?: Record<string, unknown>) => {
              void goNext(stepData);
            }}
          />
        </ScrollView>
      </KeyboardAvoidingView>
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
    backgroundColor: "#0F1E26",
  },
  dotCompleted: {
    opacity: 0.6,
  },
  scroll: {
    flex: 1,
  },
  keyboardAvoider: {
    flex: 1,
  },
  content: {
    gap: 16,
    paddingBottom: 24,
  },
  errorBanner: {
    marginTop: 8,
    padding: 12,
    borderRadius: 12,
    backgroundColor: "#FFFBEB",
  },
});

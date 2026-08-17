import { useMemo, useState } from "react";
import { Linking, ScrollView, StyleSheet, View } from "react-native";
import { Header } from "../../components/ui/Header";
import { Icon } from "../../components/ui/Icon";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { useBusiness } from "../../theme/ThemeProvider";
import { config } from "../../lib/config";
import { submitPublicQuoteRequest } from "../../api/quoteRequests";
import { BudgetContextStep } from "./quote-steps/BudgetContextStep";
import { ConfirmationStep } from "./quote-steps/ConfirmationStep";
import { ConsentsStep } from "./quote-steps/ConsentsStep";
import { ContactStep } from "./quote-steps/ContactStep";
import { ConsumerUnitQuestionnaire } from "./quote-steps/ConsumerUnitQuestionnaire";
import { EICRQuestionnaire } from "./quote-steps/EICRQuestionnaire";
import { EmergencyCallbackScreen } from "./quote-steps/EmergencyCallbackScreen";
import { EntryPostcodeStep } from "./quote-steps/EntryPostcodeStep";
import { EVChargerQuestionnaire } from "./quote-steps/EVChargerQuestionnaire";
import { JobCategoryStep } from "./quote-steps/JobCategoryStep";
import { MediaCaptureStep } from "./quote-steps/MediaCaptureStep";
import { OtherQuestionnaire } from "./quote-steps/OtherQuestionnaire";
import { PropertyProfileStep } from "./quote-steps/PropertyProfileStep";
import { UrgencyTriageStep } from "./quote-steps/UrgencyTriageStep";
import {
  evaluateTriage,
  INITIAL_FORM_DATA,
  QuoteFormData,
  TriageLevel,
} from "./quote-steps/types";

type CustomerQuoteRequestFlowProps = {
  onClose: () => void;
  onCancel?: () => void;
};

type StepDef = {
  key: string;
  label: string;
};

const STANDARD_STEPS: StepDef[] = [
  { key: "postcode", label: "Postcode" },
  { key: "contact", label: "Contact" },
  { key: "property", label: "Property" },
  { key: "category", label: "Job type" },
  { key: "questionnaire", label: "Details" },
  { key: "media", label: "Photos" },
  { key: "urgency", label: "Timing" },
  { key: "budget", label: "Budget" },
  { key: "consents", label: "Consents" },
  { key: "confirmation", label: "Done" },
];

export function CustomerQuoteRequestFlow({
  onClose,
  onCancel,
}: CustomerQuoteRequestFlowProps) {
  const { business, theme } = useBusiness();
  const [formData, setFormData] = useState<QuoteFormData>(INITIAL_FORM_DATA);
  const [stepIndex, setStepIndex] = useState(0);
  const [triage, setTriage] = useState<TriageLevel>("standard");
  const [showEmergency, setShowEmergency] = useState(false);
  const [serviceAreaError, setServiceAreaError] = useState<string | null>(null);

  const steps = useMemo<StepDef[]>(() => {
    if (showEmergency) return [...STANDARD_STEPS, { key: "emergency", label: "Emergency" }];
    return STANDARD_STEPS;
  }, [showEmergency]);

  const step = steps[stepIndex];
  const isFirst = stepIndex === 0;
  const isLast = stepIndex === steps.length - 1;

  const updateFormData = (patch: Partial<QuoteFormData>) => {
    setFormData((prev) => ({ ...prev, ...patch }));
  };

  const submitToBackend = async () => {
    // Connected mode with a resolved business: create a real quote request so it
    // lands as a lead in the tradesperson's dashboard. Non-blocking — the
    // confirmation screen still shows if the network hiccups (demo stays mock).
    if (!config.apiEnabled || !business?.slug) return;
    try {
      await submitPublicQuoteRequest(business.slug, formData);
    } catch {
      // Swallow: capture UX should not hard-fail on a flaky submit.
    }
  };

  const handleNext = () => {
    // The consents step is the last data step before confirmation; submit here.
    if (step.key === "consents") {
      void submitToBackend();
    }
    if (isLast) {
      onClose();
      return;
    }
    setStepIndex((i) => i + 1);
  };

  const handleBack = () => {
    if (showEmergency) {
      setShowEmergency(false);
      return;
    }
    if (isFirst) {
      if (onCancel) onCancel();
      else onClose();
      return;
    }
    setStepIndex((i) => Math.max(0, i - 1));
  };

  const handleUrgencyNext = () => {
    const evaluated = evaluateTriage(formData.urgency, formData.redFlagSymptoms);
    setTriage(evaluated);
    if (evaluated === "emergency") {
      setShowEmergency(true);
    }
    setStepIndex((i) => i + 1);
  };

  const handlePostcodeNext = () => {
    if (formData.inServiceArea === false) {
      setServiceAreaError(
        "This postcode is outside our service area. You can leave your details for a referral."
      );
      return;
    }
    setServiceAreaError(null);
    handleNext();
  };

  const handleEmergencyDone = () => {
    if (business?.contactPhone) {
      Linking.openURL(`tel:${business.contactPhone.replace(/\s/g, "")}`).catch(() => {
        // Ignore deep-link errors in mock
      });
    }
    onClose();
  };

  const stepProps = {
    formData,
    updateFormData,
    onNext: handleNext,
    onBack: handleBack,
    business,
  };

  const renderQuestionnaire = () => {
    switch (formData.category) {
      case "consumer_unit":
        return <ConsumerUnitQuestionnaire {...stepProps} />;
      case "ev_charger":
        return <EVChargerQuestionnaire {...stepProps} />;
      case "eicr":
        return <EICRQuestionnaire {...stepProps} />;
      default:
        return <OtherQuestionnaire {...stepProps} />;
    }
  };

  const renderStep = () => {
    if (showEmergency) {
      return (
        <EmergencyCallbackScreen
          {...stepProps}
          triage={triage}
          onDone={handleEmergencyDone}
        />
      );
    }

    switch (step.key) {
      case "postcode":
        return (
          <EntryPostcodeStep
            {...stepProps}
            serviceAreaError={serviceAreaError}
            onPostcodeNext={handlePostcodeNext}
          />
        );
      case "contact":
        return <ContactStep {...stepProps} />;
      case "property":
        return <PropertyProfileStep {...stepProps} />;
      case "category":
        return <JobCategoryStep {...stepProps} />;
      case "questionnaire":
        return renderQuestionnaire();
      case "media":
        return <MediaCaptureStep {...stepProps} />;
      case "urgency":
        return <UrgencyTriageStep {...stepProps} onNext={handleUrgencyNext} />;
      case "budget":
        return <BudgetContextStep {...stepProps} />;
      case "consents":
        return <ConsentsStep {...stepProps} />;
      case "confirmation":
        return <ConfirmationStep {...stepProps} onDone={onClose} />;
      default:
        return null;
    }
  };

  const progressDotCount = showEmergency ? STANDARD_STEPS.length + 1 : STANDARD_STEPS.length;
  const activeIndex = showEmergency ? progressDotCount - 1 : stepIndex;

  return (
    <Screen testID="customer-quote-flow" style={styles.container}>
      <Header
        title={business?.name ?? "Request a quote"}
        onBack={isFirst && !showEmergency ? onCancel ?? onClose : handleBack}
        rightAction={
          business?.logoUrl ? (
            <Icon name="checkmark" size={24} color={theme.colors.primary} />
          ) : null
        }
      />

      <View style={styles.progress}>
        {Array.from({ length: progressDotCount }).map((_, index) => {
          const isActive = index <= activeIndex;
          const isEmergencyDot = showEmergency && index === activeIndex;
          return (
            <View
              key={index}
              style={[
                styles.dot,
                isActive && (isEmergencyDot ? styles.dotEmergency : styles.dotActive),
              ]}
            />
          );
        })}
      </View>

      <Text variant="caption" color="secondary" style={styles.stepLabel}>
        Step {activeIndex + 1} of {progressDotCount}: {step.label}
      </Text>

      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
      >
        {renderStep()}
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  container: {
    paddingVertical: 24,
  },
  progress: {
    flexDirection: "row",
    gap: 8,
    marginBottom: 12,
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
  dotEmergency: {
    backgroundColor: "#EF4444",
  },
  stepLabel: {
    marginBottom: 12,
  },
  scroll: {
    flex: 1,
  },
  scrollContent: {
    flexGrow: 1,
    paddingBottom: 24,
  },
});

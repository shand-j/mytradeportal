import { useMemo, useState } from "react";
import { Linking, ScrollView, StyleSheet, View } from "react-native";
import { useQueryClient } from "@tanstack/react-query";
import { Header } from "../../components/ui/Header";
import { Icon } from "../../components/ui/Icon";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { useAuth } from "../../contexts/AuthContext";
import { useBusiness } from "../../theme/ThemeProvider";
import { submitPublicQuoteRequest, PublicQuoteRequestAck } from "../../api/quoteRequests";
import { AccountCreationStep } from "./quote-steps/AccountCreationStep";
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
  const { role } = useAuth();
  const { business, theme } = useBusiness();
  const queryClient = useQueryClient();
  const [formData, setFormData] = useState<QuoteFormData>(INITIAL_FORM_DATA);
  const [stepIndex, setStepIndex] = useState(0);
  const [triage, setTriage] = useState<TriageLevel>("standard");
  const [showEmergency, setShowEmergency] = useState(false);
  const [serviceAreaError, setServiceAreaError] = useState<string | null>(null);
  const [submittedAck, setSubmittedAck] = useState<PublicQuoteRequestAck | null>(null);

  const needsAccount = role !== "customer";
  const steps = useMemo<StepDef[]>(() => {
    const base = needsAccount
      ? [...STANDARD_STEPS, { key: "account", label: "Account" }]
      : STANDARD_STEPS;
    if (showEmergency) return [...base, { key: "emergency", label: "Emergency" }];
    return base;
  }, [showEmergency, needsAccount]);

  // Guard against the steps array shrinking while stepIndex still points at an
  // old last index. This happens when the customer just created an account and
  // the "account" step is removed before the flow finishes closing.
  const step = steps[Math.min(stepIndex, steps.length - 1)] ?? { key: "confirmation", label: "Done" };
  const isFirst = stepIndex === 0;
  const isLast = stepIndex === steps.length - 1;

  const updateFormData = (patch: Partial<QuoteFormData>) => {
    setFormData((prev) => ({ ...prev, ...patch }));
  };

  const submitToBackend = async () => {
    // With a resolved business: create a real quote request so it lands as a lead
    // in the tradesperson's dashboard. Non-blocking — the confirmation screen
    // still shows if the network hiccups.
    if (!business?.slug) return;
    try {
      const ack = await submitPublicQuoteRequest(business.slug, formData);
      setSubmittedAck(ack);
      // Refresh the customer's history and the trade leads list so the new
      // request appears on both sides immediately.
      queryClient.invalidateQueries({ queryKey: ["my-requests"] });
      queryClient.invalidateQueries({ queryKey: ["quote-requests"] });
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
        // Ignore deep-link errors.
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
        return (
          <ConfirmationStep
            {...stepProps}
            showCreateAccount={needsAccount}
            onDone={needsAccount ? handleNext : onClose}
          />
        );
      case "account":
        if (!submittedAck) return null;
        return <AccountCreationStep {...stepProps} quoteRequestId={submittedAck.id} />;
      default:
        return null;
    }
  };

  const progressDotCount = steps.length;
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
                { backgroundColor: isActive ? (isEmergencyDot ? theme.colors.error : theme.colors.primary) : theme.colors.border },
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

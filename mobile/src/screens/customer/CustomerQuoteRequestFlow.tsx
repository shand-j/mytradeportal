import { useEffect, useMemo, useRef, useState } from "react";
import { KeyboardAvoidingView, Linking, Platform, ScrollView, StyleSheet, View } from "react-native";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Header } from "../../components/ui/Header";
import { Icon } from "../../components/ui/Icon";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { useAuth } from "../../contexts/AuthContext";
import { useBusiness } from "../../theme/ThemeProvider";
import { submitPublicQuoteRequest, PublicQuoteRequestAck } from "../../api/quoteRequests";
import { stagedPhotosFromMedia, uploadCustomerPhotos } from "../../api/uploads";
import { fetchCustomerMe } from "../../api/auth";
import { ApiError, NetworkError } from "../../lib/apiClient";
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
  PropertyProfile,
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

/** Human-readable submit failure for the blocking error on the consents step. */
function submitErrorMessage(err: unknown): string {
  if (err instanceof NetworkError) {
    return "No connection — check your internet and tap retry.";
  }
  if (err instanceof ApiError) {
    if (err.status === 429) {
      return "Too many attempts just now — wait a minute and tap retry.";
    }
    if (err.detail) {
      // Server details can carry a stable machine prefix ("customer_blocked: …")
      // that clients key on — drop it from the human-readable message.
      return err.detail.replace(/^[a-z_]+:\s*/i, "");
    }
  }
  return "Your request could not be sent. Please try again.";
}

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
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const prefilledRef = useRef(false);

  // Logged-in customers get their saved details pre-filled (still editable) so
  // repeat quote requests don't re-ask for postcode, contact or property info.
  const { data: me } = useQuery({
    queryKey: ["customer-me"],
    queryFn: fetchCustomerMe,
    enabled: role === "customer",
  });
  useEffect(() => {
    if (!me || prefilledRef.current) return;
    prefilledRef.current = true;
    const saved = (me.propertyProfile ?? {}) as Partial<PropertyProfile>;
    setFormData((prev) => ({
      ...prev,
      postcode: me.postcode || prev.postcode,
      contact: {
        ...prev.contact,
        name: me.fullName || prev.contact.name,
        email: me.email || prev.contact.email,
        mobile: me.phone || prev.contact.mobile,
      },
      property: { ...prev.property, ...saved },
    }));
  }, [me]);

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

  const submitToBackend = async (): Promise<boolean> => {
    // With a resolved business: create a real quote request so it lands as a lead
    // in the tradesperson's dashboard. A failure must block the confirmation
    // screen — the homeowner has to know their request never arrived.
    if (!business?.slug) {
      setSubmitError("We couldn't identify the business. Go back and find your electrician again.");
      return false;
    }
    try {
      const ack = await submitPublicQuoteRequest(business.slug, formData);
      if (!ack?.id || !ack.reference) {
        throw new Error("Quote request ack was missing its id/reference");
      }
      setSubmittedAck(ack);
      // Logged-in customers already hold a token (and the request is linked to
      // their account), so staged photos can go up right away. Guests upload
      // after account creation in AccountCreationStep instead.
      if (role === "customer") {
        void uploadCustomerPhotos(ack.id, stagedPhotosFromMedia(formData.media));
      }
      // Refresh the customer's history and the trade leads list so the new
      // request appears on both sides immediately.
      queryClient.invalidateQueries({ queryKey: ["my-requests"] });
      queryClient.invalidateQueries({ queryKey: ["quote-requests"] });
      return true;
    } catch (err) {
      console.error("[quote-request] submit failed", {
        slug: business.slug,
        error: err instanceof Error ? { name: err.name, message: err.message } : err,
        status: err instanceof ApiError ? err.status : undefined,
      });
      setSubmitError(submitErrorMessage(err));
      return false;
    }
  };

  const handleConsentsNext = () => {
    // Resubmitting after a success would create a duplicate lead — a confirmed
    // request just moves on to the confirmation screen.
    if (submittedAck) {
      setStepIndex((i) => i + 1);
      return;
    }
    if (submitting) return;
    setSubmitting(true);
    setSubmitError(null);
    void submitToBackend().then((ok) => {
      setSubmitting(false);
      // Only a real ack advances past consents; failures stay put with the
      // error + retry on the consents screen.
      if (ok) setStepIndex((i) => i + 1);
    });
  };

  const handleNext = () => {
    // The consents step is the last data step before confirmation; submit here
    // and gate advancement on a real acknowledgement.
    if (step.key === "consents") {
      handleConsentsNext();
      return;
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
        return <ConsentsStep {...stepProps} submitting={submitting} submitError={submitError} />;
      case "confirmation":
        // The confirmation screen is only meaningful with a real backend ack;
        // without one the request never arrived, so show the consents screen
        // again (with its blocking error + retry) instead of a false success.
        if (!submittedAck) {
          return (
            <ConsentsStep
              {...stepProps}
              onNext={handleConsentsNext}
              submitting={submitting}
              submitError={submitError}
            />
          );
        }
        return (
          <ConfirmationStep
            {...stepProps}
            reference={submittedAck.reference}
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

      <KeyboardAvoidingView
        style={styles.keyboardAvoider}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <ScrollView
          style={styles.scroll}
          contentContainerStyle={styles.scrollContent}
          keyboardShouldPersistTaps="handled"
        >
          {renderStep()}
        </ScrollView>
      </KeyboardAvoidingView>
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
  keyboardAvoider: {
    flex: 1,
  },
  scrollContent: {
    flexGrow: 1,
    paddingBottom: 24,
  },
});

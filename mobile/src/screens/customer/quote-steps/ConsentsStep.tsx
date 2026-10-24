import { Pressable, StyleSheet, View } from "react-native";
import { Button } from "../../../components/ui/Button";
import { Icon } from "../../../components/ui/Icon";
import { Text } from "../../../components/ui/Text";
import { useBusiness } from "../../../theme/ThemeProvider";
import { StepPropsWithBusiness } from "./types";

function Checkbox({
  label,
  checked,
  onToggle,
  testID,
}: {
  label: string;
  checked: boolean;
  onToggle: () => void;
  testID?: string;
}) {
  return (
    <Pressable testID={testID} onPress={onToggle} style={styles.checkboxRow}>
      <View style={[styles.checkbox, checked && styles.checkboxChecked]}>
        {checked ? <Icon name="checkmark" size={16} color="#FFFFFF" /> : null}
      </View>
      <Text variant="body" style={styles.checkboxLabel}>
        {label}
      </Text>
    </Pressable>
  );
}

type ConsentsStepProps = StepPropsWithBusiness & {
  /** True while the quote request is being submitted to the backend. */
  submitting?: boolean;
  /** Blocking submit failure; the user stays on this step until retry succeeds. */
  submitError?: string | null;
};

export function ConsentsStep({
  formData,
  updateFormData,
  onNext,
  submitting = false,
  submitError = null,
}: ConsentsStepProps) {
  const { business } = useBusiness();
  // Controlled: write every toggle straight to the parent form so the submit
  // that fires on "Next" always reads the latest consents.
  const consents = formData.consents;
  const isTenant = formData.property.tenure === "tenant";

  const update = (key: string, value: boolean) => {
    updateFormData({ consents: { ...consents, [key]: value } });
  };

  const canSubmit =
    !submitting &&
    consents.termsPrivacy &&
    consents.contactPermission &&
    (!isTenant || consents.landlordPermission);

  return (
    <View style={styles.container}>
      <Text variant="title" weight="bold">
        Consents
      </Text>
      <Text variant="body" color="secondary">
        You control how {business?.name ?? "we"} contact you.
      </Text>

      <Checkbox
        testID="quote-consent-terms"
        label="I agree to the Terms of Service and Privacy Policy."
        checked={consents.termsPrivacy}
        onToggle={() => update("termsPrivacy", !consents.termsPrivacy)}
      />

      <Checkbox
        testID="quote-consent-contact"
        label="I agree to be contacted about this quote and related work."
        checked={consents.contactPermission}
        onToggle={() => update("contactPermission", !consents.contactPermission)}
      />

      <Checkbox
        testID="quote-consent-marketing"
        label="Send me occasional marketing and offers (optional)."
        checked={consents.marketingOptIn}
        onToggle={() => update("marketingOptIn", !consents.marketingOptIn)}
      />

      {isTenant ? (
        <Checkbox
          testID="quote-consent-landlord"
          label="I have my landlord’s permission to arrange this work."
          checked={consents.landlordPermission}
          onToggle={() => update("landlordPermission", !consents.landlordPermission)}
        />
      ) : null}

      {submitError ? (
        <View testID="quote-submit-error" style={styles.errorBanner}>
          <Icon name="warning" size={18} color="#B91C1C" />
          <Text variant="body" style={styles.errorText}>
            {submitError}
          </Text>
        </View>
      ) : null}

      <Button
        testID="quote-submit"
        title={submitting ? "Sending…" : submitError ? "Retry" : "Submit quote request"}
        onPress={onNext}
        disabled={!canSubmit}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: 16,
  },
  checkboxRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 12,
    paddingVertical: 4,
  },
  checkbox: {
    width: 24,
    height: 24,
    borderRadius: 6,
    borderWidth: 2,
    borderColor: "#D1D5DB",
    alignItems: "center",
    justifyContent: "center",
    marginTop: 2,
  },
  checkboxChecked: {
    backgroundColor: "#0F1E26",
    borderColor: "#0F1E26",
  },
  checkboxLabel: {
    flex: 1,
  },
  errorBanner: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    padding: 12,
    borderRadius: 12,
    backgroundColor: "#FEF2F2",
    alignSelf: "stretch",
  },
  errorText: {
    flex: 1,
    color: "#B91C1C",
  },
});

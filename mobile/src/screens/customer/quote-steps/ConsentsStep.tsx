import { useState } from "react";
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

export function ConsentsStep({ formData, updateFormData, onNext }: StepPropsWithBusiness) {
  const { business } = useBusiness();
  const [consents, setConsents] = useState(formData.consents);
  const isTenant = formData.property.tenure === "tenant";

  const update = (key: string, value: boolean) => {
    setConsents((prev) => ({ ...prev, [key]: value }));
  };

  const handleNext = () => {
    updateFormData({ consents });
    onNext();
  };

  const canSubmit =
    consents.termsPrivacy && consents.contactPermission && (!isTenant || consents.landlordPermission);

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

      <Button
        testID="quote-submit"
        title="Submit quote request"
        onPress={handleNext}
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
    backgroundColor: "#2563EB",
    borderColor: "#2563EB",
  },
  checkboxLabel: {
    flex: 1,
  },
});

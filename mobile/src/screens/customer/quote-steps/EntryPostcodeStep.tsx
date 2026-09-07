import { useState } from "react";
import { StyleSheet, TextInput, View } from "react-native";
import { Button } from "../../../components/ui/Button";
import { FormField } from "../../../components/ui/FormField";
import { Text } from "../../../components/ui/Text";
import { useBusiness } from "../../../theme/ThemeProvider";
import { StepPropsWithBusiness } from "./types";

const UK_POSTCODE_REGEX = /^[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}$/i;

type EntryPostcodeStepProps = StepPropsWithBusiness & {
  serviceAreaError: string | null;
  onPostcodeNext: () => void;
};

export function EntryPostcodeStep({
  formData,
  updateFormData,
  onPostcodeNext,
  serviceAreaError,
}: EntryPostcodeStepProps) {
  const { business } = useBusiness();
  const [postcode, setPostcode] = useState(formData.postcode);

  const isValid = UK_POSTCODE_REGEX.test(postcode.trim());

  const checkArea = () => {
    if (!isValid) return;
    // TODO: call backend service-area endpoint before setting inServiceArea.
    updateFormData({ postcode: postcode.toUpperCase(), inServiceArea: true });
    onPostcodeNext();
  };

  return (
    <View style={styles.container}>
      <Text variant="title" weight="bold" align="center">
        Get a quote from {business?.name ?? "your electrician"}
      </Text>
      <Text variant="body" color="secondary" align="center">
        Enter your postcode to check we cover your area.
      </Text>

      <FormField
        label="Postcode"
        value={postcode}
        onChangeText={setPostcode}
        placeholder="e.g. SK8 3NJ"
        autoCapitalize="characters"
        maxLength={8}
        testID="quote-postcode-input"
      />

      {serviceAreaError ? (
        <Text variant="caption" color="warning" align="center">
          {serviceAreaError}
        </Text>
      ) : null}

      <Button
        testID="quote-check-area"
        title="Continue"
        onPress={checkArea}
        disabled={!isValid}
      />
      <Button
        testID="quote-sign-in"
        title="Already have a quote? Sign in"
        variant="ghost"
        onPress={() => {
          // TODO: navigate to customer sign-in.
        }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: 16,
  },
});

import { useState } from "react";
import { StyleSheet, View } from "react-native";
import { Button } from "../../../components/ui/Button";
import { FormField } from "../../../components/ui/FormField";
import { Text } from "../../../components/ui/Text";
import { StepPropsWithBusiness } from "./types";

const PREFERRED_CONTACTS = [
  { key: "in_app_chat", label: "Online chat" },
  { key: "phone", label: "Phone" },
  { key: "email", label: "Email" },
];

const BEST_TIMES = [
  { key: "morning", label: "Morning" },
  { key: "afternoon", label: "Afternoon" },
  { key: "evening", label: "Evening" },
];

export function ContactStep({ formData, updateFormData, onNext }: StepPropsWithBusiness) {
  const [contact, setContact] = useState(formData.contact);

  const toggleBestTime = (key: string) => {
    setContact((prev) => {
      const times = prev.bestTimeToCall.includes(key)
        ? prev.bestTimeToCall.filter((k) => k !== key)
        : [...prev.bestTimeToCall, key];
      return { ...prev, bestTimeToCall: times };
    });
  };

  const handleNext = () => {
    updateFormData({ contact });
    onNext();
  };

  const isValid =
    contact.name.trim().length > 0 &&
    contact.email.trim().length > 0 &&
    contact.email.includes("@") &&
    contact.preferredContact.length > 0;

  return (
    <View style={styles.container}>
      <Text variant="title" weight="bold">
        Your contact details
      </Text>
      <Text variant="body" color="secondary">
        We need this to send your quote and keep you updated.
      </Text>

      <FormField
        label="Full name"
        value={contact.name}
        onChangeText={(text) => setContact((prev) => ({ ...prev, name: text }))}
        testID="quote-name-input"
      />
      <FormField
        label="Mobile"
        value={contact.mobile}
        onChangeText={(text) => setContact((prev) => ({ ...prev, mobile: text }))}
        keyboardType="phone-pad"
        testID="quote-phone-input"
      />
      <FormField
        label="Email"
        value={contact.email}
        onChangeText={(text) => setContact((prev) => ({ ...prev, email: text }))}
        keyboardType="email-address"
        autoCapitalize="none"
        testID="quote-email-input"
      />

      <Text variant="body" weight="semibold">
        Preferred contact method
      </Text>
      <View style={styles.options}>
        {PREFERRED_CONTACTS.map((option) => (
          <Button
            key={option.key}
            title={option.label}
            variant={contact.preferredContact === option.key ? "primary" : "outline"}
            size="sm"
            onPress={() => setContact((prev) => ({ ...prev, preferredContact: option.key as any }))}
          />
        ))}
      </View>

      {contact.preferredContact === "phone" ? (
        <>
          <Text variant="body" weight="semibold">
            Best time to call
          </Text>
          <View style={styles.options}>
            {BEST_TIMES.map((option) => (
              <Button
                key={option.key}
                title={option.label}
                variant={contact.bestTimeToCall.includes(option.key) ? "primary" : "outline"}
                size="sm"
                onPress={() => toggleBestTime(option.key)}
              />
            ))}
          </View>
        </>
      ) : null}

      <Button testID="quote-contact-continue" title="Continue" onPress={handleNext} disabled={!isValid} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: 16,
  },
  options: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
});

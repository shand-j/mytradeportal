import { useState } from "react";
import { StyleSheet, TextInput, View } from "react-native";
import { Button } from "../../../components/ui/Button";
import { FileUploadMock } from "../../../components/ui/FileUploadMock";
import { Text } from "../../../components/ui/Text";
import { StepPropsWithBusiness } from "./types";

export function OtherQuestionnaire({ formData, updateFormData, onNext }: StepPropsWithBusiness) {
  const [description, setDescription] = useState(
    (formData.questionnaire.other_description as string) ?? ""
  );
  const [photosUploaded, setPhotosUploaded] = useState(
    (formData.questionnaire.other_photos_uploaded as boolean) ?? false
  );

  const handleNext = () => {
    updateFormData({
      questionnaire: {
        ...formData.questionnaire,
        other_description: description,
        other_photos_uploaded: photosUploaded,
        requires_human_review: true,
      },
    });
    onNext();
  };

  const isValid = description.trim().length >= 30 && photosUploaded;

  return (
    <View style={styles.container}>
      <Text variant="title" weight="bold">
        Tell us about your job
      </Text>
      <Text variant="body" color="secondary">
        Because this work is bespoke, we’ll review it carefully before quoting.
      </Text>

      <Text variant="body" weight="semibold">
        What do you need done?
      </Text>
      <TextInput
        style={styles.notesInput}
        placeholder="Describe the work in at least 30 characters..."
        value={description}
        onChangeText={setDescription}
        multiline
        numberOfLines={5}
      />
      {description.trim().length > 0 && description.trim().length < 30 ? (
        <Text variant="caption" color="warning">
          Please add a bit more detail so we can prepare an accurate quote.
        </Text>
      ) : null}

      <Text variant="body" weight="semibold">
        Required photos
      </Text>
      <FileUploadMock
        label={photosUploaded ? "Photo uploaded" : "Upload a photo of the area"}
        fileName="other-job.jpg"
        testID="quote-other-photo"
      />
      <Button
        title={photosUploaded ? "Remove photo" : "Mock photo uploaded"}
        variant="outline"
        size="sm"
        onPress={() => setPhotosUploaded((v) => !v)}
      />

      <Text variant="caption" color="secondary">
        This request will always be reviewed by an electrician before a quote is sent.
      </Text>

      <Button testID="quote-other-continue" title="Continue" onPress={handleNext} disabled={!isValid} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: 16,
  },
  notesInput: {
    height: 120,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#E5E7EB",
    backgroundColor: "#FFFFFF",
    padding: 12,
    fontSize: 14,
    textAlignVertical: "top",
  },
});

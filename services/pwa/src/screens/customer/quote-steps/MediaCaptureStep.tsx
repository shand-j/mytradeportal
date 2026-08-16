import { useState } from "react";
import { StyleSheet, View } from "react-native";
import { Button } from "../../../components/ui/Button";
import { FileUploadMock } from "../../../components/ui/FileUploadMock";
import { Icon } from "../../../components/ui/Icon";
import { Text } from "../../../components/ui/Text";
import { MediaItem, StepPropsWithBusiness } from "./types";

export function MediaCaptureStep({ formData, updateFormData, onNext }: StepPropsWithBusiness) {
  const [media, setMedia] = useState<MediaItem[]>(formData.media);

  const addPhoto = () => {
    const next: MediaItem = {
      id: Date.now().toString(),
      label: `Photo ${media.length + 1}`,
      type: "image",
    };
    setMedia((prev) => [...prev, next]);
  };

  const addVideo = () => {
    const next: MediaItem = {
      id: (Date.now() + 1).toString(),
      label: "Walkthrough video",
      type: "video",
    };
    setMedia((prev) => [...prev, next]);
  };

  const handleNext = () => {
    updateFormData({ media });
    onNext();
  };

  const requiredLabel =
    formData.category === "consumer_unit"
      ? "Consumer unit photo required"
      : formData.category === "ev_charger"
      ? "Driveway / charger location photos required"
      : formData.category === "other"
      ? "Photos required for bespoke jobs"
      : "Photos recommended";

  return (
    <View style={styles.container}>
      <Text variant="title" weight="bold">
        Add photos or video
      </Text>
      <Text variant="body" color="secondary">
        Photos help your electrician quote accurately without a site visit.
      </Text>

      <View style={styles.guide}>
        <Icon name="info" size={20} color="#2563EB" />
        <Text variant="caption" color="primary">
          {requiredLabel}
        </Text>
      </View>

      <View style={styles.mediaGrid}>
        {media.map((item) => (
          <View key={item.id} style={styles.mediaThumb}>
            <Icon name={item.type === "video" ? "video" : "image"} size={24} color="#6B7280" />
            <Text variant="caption" color="secondary" numberOfLines={1}>
              {item.label}
            </Text>
          </View>
        ))}
        <Button title="+ Add photo" variant="outline" onPress={addPhoto} />
      </View>

      <FileUploadMock label="Upload document (EICR, plans, etc.)" fileName="document.pdf" />

      <Button title="+ Add 60-second video walkthrough" variant="outline" onPress={addVideo} />

      <Button testID="quote-media-continue" title="Continue" onPress={handleNext} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: 16,
  },
  guide: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    padding: 12,
    borderRadius: 12,
    backgroundColor: "#EFF6FF",
  },
  mediaGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  mediaThumb: {
    width: 80,
    height: 80,
    borderRadius: 12,
    backgroundColor: "#F3F4F6",
    alignItems: "center",
    justifyContent: "center",
    gap: 4,
    padding: 8,
  },
});

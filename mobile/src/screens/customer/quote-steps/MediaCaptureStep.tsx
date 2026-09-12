import { useState } from "react";
import { Image, Pressable, StyleSheet, View } from "react-native";
import * as ImagePicker from "expo-image-picker";
import { Button } from "../../../components/ui/Button";
import { Icon } from "../../../components/ui/Icon";
import { Text } from "../../../components/ui/Text";
import { MediaItem, StepPropsWithBusiness } from "./types";

export function MediaCaptureStep({ formData, updateFormData, onNext }: StepPropsWithBusiness) {
  const [media, setMedia] = useState<MediaItem[]>(formData.media);
  const [error, setError] = useState<string | null>(null);

  const addPhotos = async () => {
    setError(null);
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      setError("Photo library access denied");
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ["images"],
      quality: 0.7,
      allowsMultipleSelection: true,
    });
    if (result.canceled || result.assets.length === 0) return;
    const stamp = Date.now();
    const picked: MediaItem[] = result.assets.map((asset, index) => ({
      id: `${stamp}-${index}`,
      label: asset.fileName ?? `Photo ${media.length + index + 1}`,
      type: "image",
      localUri: asset.uri,
      fileName: asset.fileName ?? `photo-${stamp}-${index}.jpg`,
      mimeType: asset.mimeType ?? "image/jpeg",
      sizeBytes: asset.fileSize,
    }));
    setMedia((prev) => [...prev, ...picked]);
  };

  const removePhoto = (id: string) => {
    setMedia((prev) => prev.filter((item) => item.id !== id));
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
        Add photos
      </Text>
      <Text variant="body" color="secondary">
        Photos help your electrician quote accurately without a site visit.
      </Text>

      <View style={styles.guide}>
        <Icon name="info" size={20} color="#0F1E26" />
        <Text variant="caption" color="primary">
          {requiredLabel}
        </Text>
      </View>

      <View style={styles.mediaGrid}>
        {media.map((item) => (
          <View key={item.id} style={styles.mediaThumbWrap}>
            {item.localUri ? (
              <Image source={{ uri: item.localUri }} style={styles.mediaThumb} />
            ) : (
              <View style={[styles.mediaThumb, styles.mediaThumbFallback]}>
                <Icon name="image" size={24} color="#6B7280" />
              </View>
            )}
            <Pressable
              testID={`quote-media-remove-${item.id}`}
              onPress={() => removePhoto(item.id)}
              style={styles.removeBadge}
            >
              <Icon name="close" size={14} color="#FFFFFF" />
            </Pressable>
          </View>
        ))}
      </View>

      <Button testID="quote-media-add-photo" title="Add photo" variant="outline" onPress={addPhotos} />
      {error ? (
        <Text variant="caption" color="warning">
          {error}
        </Text>
      ) : null}

      <Button title="Video upload coming soon" variant="outline" disabled />

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
    backgroundColor: "#F2F5F6",
  },
  mediaGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  mediaThumbWrap: {
    position: "relative",
  },
  mediaThumb: {
    width: 80,
    height: 80,
    borderRadius: 12,
    backgroundColor: "#F3F4F6",
  },
  mediaThumbFallback: {
    alignItems: "center",
    justifyContent: "center",
  },
  removeBadge: {
    position: "absolute",
    top: -4,
    right: -4,
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: "#1F2937",
    alignItems: "center",
    justifyContent: "center",
  },
});

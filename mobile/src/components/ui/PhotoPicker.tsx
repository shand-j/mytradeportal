import { useState } from "react";
import { Pressable, View } from "react-native";
import * as ImagePicker from "expo-image-picker";
import { Image } from "expo-image";
import { Icon } from "./Icon";
import { Text } from "./Text";
import { uploadFileToApi } from "../../api/uploads";

type PhotoAsset = {
  url: string;
  key: string;
};

type PhotoPickerProps = {
  photos: PhotoAsset[];
  onChange: (photos: PhotoAsset[]) => void;
  maxPhotos?: number;
  testID?: string;
};

async function uploadPhoto(asset: ImagePicker.ImagePickerAsset): Promise<PhotoAsset> {
  const filename = asset.fileName ?? `photo-${Date.now()}.jpg`;
  const contentType = asset.mimeType ?? "image/jpeg";
  // MinIO is private-network-only: uploads go through the API, which returns
  // the storage key + API-proxied download URL.
  return uploadFileToApi("/files/upload", { uri: asset.uri, name: filename, type: contentType });
}

export function PhotoPicker({ photos, onChange, maxPhotos = 5, testID }: PhotoPickerProps) {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const canAdd = photos.length < maxPhotos && !uploading;

  const pick = async () => {
    setError(null);
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      setError("Photo library access denied");
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.7,
      allowsMultipleSelection: false,
    });
    if (result.canceled || result.assets.length === 0) return;
    setUploading(true);
    try {
      const uploaded = await uploadPhoto(result.assets[0]);
      onChange([...photos, uploaded]);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setUploading(false);
    }
  };

  const removeAt = (index: number) => {
    const next = photos.slice();
    next.splice(index, 1);
    onChange(next);
  };

  return (
    <View testID={testID} className="gap-3">
      {photos.length > 0 && (
        <View className="flex-row flex-wrap gap-2">
          {photos.map((photo, idx) => (
            <View key={photo.key} className="relative">
              <Image
                source={{ uri: photo.url }}
                style={{ width: 80, height: 80, borderRadius: 8 }}
                contentFit="cover"
              />
              <Pressable
                onPress={() => removeAt(idx)}
                testID={`photo-remove-${idx}`}
                className="absolute -right-1 -top-1 h-6 w-6 items-center justify-center rounded-full bg-slate-800"
              >
                <Icon name="close" size={14} color="#FFFFFF" />
              </Pressable>
            </View>
          ))}
        </View>
      )}
      <Pressable
        onPress={canAdd ? pick : undefined}
        testID="photo-add"
        className={`flex-row items-center gap-3 rounded-xl border border-dashed p-4 ${
          canAdd ? "border-slate-300 bg-slate-50" : "border-slate-200 bg-slate-100 opacity-60"
        }`}
      >
        <Icon name={uploading ? "cloud-done" : "image"} size={24} color="#B27E00" />
        <View className="flex-1">
          <Text variant="body" weight="semibold" numberOfLines={1}>
            {uploading ? "Uploading…" : "Add photo"}
          </Text>
          <Text variant="caption" color="secondary">
            {photos.length === 0
              ? "Optional — helps the AI price accurately"
              : `${photos.length}/${maxPhotos} attached`}
          </Text>
        </View>
      </Pressable>
      {error && (
        <Text variant="caption" style={{ color: "#DC2626" }}>
          {error}
        </Text>
      )}
    </View>
  );
}

export type { PhotoAsset };

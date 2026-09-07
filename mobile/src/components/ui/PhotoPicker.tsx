import { useState } from "react";
import { Pressable, View } from "react-native";
import * as ImagePicker from "expo-image-picker";
import { Image } from "expo-image";
import { Icon } from "./Icon";
import { Text } from "./Text";
import { api } from "../../lib/apiClient";

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

type PresignedUploadResponse = {
  url: string;
  fields: Record<string, string>;
  key: string;
};

async function uploadToPresigned(asset: ImagePicker.ImagePickerAsset): Promise<PhotoAsset> {
  const filename = asset.fileName ?? `photo-${Date.now()}.jpg`;
  const contentType = asset.mimeType ?? "image/jpeg";
  const presigned = await api.post<PresignedUploadResponse>("/files/presigned-upload", {
    filename,
    content_type: contentType,
  });
  const form = new FormData();
  Object.entries(presigned.fields).forEach(([key, value]) => form.append(key, value));
  // React Native and web File / Blob shapes differ; both are accepted by
  // FormData under `any` here without runtime pain.
  const file =
    typeof File !== "undefined"
      ? await fetch(asset.uri).then((r) => r.blob()).then((blob) => blob)
      : ({ uri: asset.uri, name: filename, type: contentType } as unknown as Blob);
  form.append("file", file as Blob, filename);
  const response = await fetch(presigned.url, { method: "POST", body: form });
  if (!response.ok) {
    throw new Error(`Upload failed (${response.status})`);
  }
  return { url: `${presigned.url}/${presigned.key}`, key: presigned.key };
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
      const uploaded = await uploadToPresigned(result.assets[0]);
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
        <Icon name={uploading ? "cloud-done" : "image"} size={24} color="#4F46E5" />
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

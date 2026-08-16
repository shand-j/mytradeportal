import { useState } from "react";
import { Pressable, View } from "react-native";
import { Icon } from "./Icon";
import { Text } from "./Text";

export function FileUploadMock({
  label = "Upload file",
  fileName = "document.pdf",
  testID,
}: {
  label?: string;
  fileName?: string;
  testID?: string;
}) {
  const [uploaded, setUploaded] = useState(false);

  return (
    <Pressable
      testID={testID}
      onPress={() => setUploaded((prev) => !prev)}
      className="flex-row items-center gap-3 rounded-xl border border-dashed border-slate-300 bg-slate-50 p-4"
    >
      <Icon name={uploaded ? "checkmark" : "add"} size={24} color="#2563EB" />
      <View className="flex-1">
        <Text variant="body" weight="semibold" numberOfLines={1}>
          {uploaded ? fileName : label}
        </Text>
        <Text variant="caption" color="secondary">
          {uploaded ? "Tap to remove" : "Tap to mock upload"}
        </Text>
      </View>
    </Pressable>
  );
}

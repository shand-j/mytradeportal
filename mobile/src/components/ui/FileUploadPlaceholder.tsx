import { View } from "react-native";
import { Icon } from "./Icon";
import { Text } from "./Text";

type FileUploadPlaceholderProps = {
  label?: string;
  testID?: string;
};

export function FileUploadPlaceholder({
  label = "Upload file",
  testID,
}: FileUploadPlaceholderProps) {
  return (
    <View
      testID={testID}
      className="flex-row items-center gap-3 rounded-xl border border-dashed border-slate-300 bg-slate-50 p-4 opacity-60"
    >
      <Icon name="cloud-offline" size={24} color="#6B7280" />
      <View className="flex-1">
        <Text variant="body" weight="semibold" numberOfLines={1}>
          {label}
        </Text>
        <Text variant="caption" color="secondary">
          Upload not implemented
        </Text>
      </View>
    </View>
  );
}

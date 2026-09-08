import { useRouter } from "expo-router";
import { IconButton } from "./IconButton";

/** Three-dots shortcut to Settings, shown in the header of every main tab page. */
export function SettingsMenuButton() {
  const router = useRouter();
  return (
    <IconButton
      testID="header-settings"
      icon="more"
      size={24}
      color="#374151"
      onPress={() => router.push("/(trade)/settings")}
      accessibilityLabel="Settings"
    />
  );
}

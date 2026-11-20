import { useEffect, useRef } from "react";
import { Animated, Easing, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Icon } from "./ui/Icon";
import { Text } from "./ui/Text";
import { useOfflineStore } from "../stores/offlineStore";

/**
 * Global connectivity toast. Floats above the tab bar when the device is
 * offline (work saved locally), while syncing a backlog, and briefly after a
 * sync completes. Absolutely positioned so it never disturbs screen layout.
 * Hidden when online with an empty queue.
 */
export function OfflineBanner() {
  const insets = useSafeAreaInsets();
  const isOnline = useOfflineStore((s) => s.isOnline);
  const syncing = useOfflineStore((s) => s.syncing);
  const justSynced = useOfflineStore((s) => s.justSynced);
  const pending = useOfflineStore((s) => s.pendingCount());

  const spin = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (syncing) {
      const loop = Animated.loop(
        Animated.timing(spin, {
          toValue: 1,
          duration: 900,
          easing: Easing.linear,
          useNativeDriver: true,
        })
      );
      loop.start();
      return () => loop.stop();
    }
    spin.setValue(0);
  }, [syncing, spin]);

  const rotate = spin.interpolate({ inputRange: [0, 1], outputRange: ["0deg", "360deg"] });

  const visible = !isOnline || syncing || justSynced;
  if (!visible) return null;

  let bg = "#1F2937";
  let iconName: "cloud-offline" | "sync" | "cloud-done" = "cloud-offline";
  let iconColor = "#FCD34D";
  let title = "You're offline";
  let subtitle =
    pending > 0
      ? `${pending} change${pending === 1 ? "" : "s"} saved on this device`
      : "Work is saved on this device";

  if (isOnline && syncing) {
    bg = "#0F1E26";
    iconName = "sync";
    iconColor = "#FFFFFF";
    title = "Back online — syncing";
    subtitle = `Uploading ${pending || "your"} change${pending === 1 ? "" : "s"}…`;
  } else if (isOnline && justSynced) {
    bg = "#0F1E26";
    iconName = "cloud-done";
    iconColor = "#FFC107";
    title = "All changes synced";
    subtitle = "Everything captured offline is saved to the cloud";
  }

  return (
    <View
      testID="offline-banner"
      pointerEvents="none"
      style={{
        position: "absolute",
        left: 12,
        right: 12,
        bottom: insets.bottom + 78,
        zIndex: 100,
      }}
    >
      <View
        style={{
          flexDirection: "row",
          alignItems: "center",
          gap: 10,
          paddingHorizontal: 14,
          paddingVertical: 12,
          backgroundColor: bg,
          borderRadius: 16,
          shadowColor: "#000",
          shadowOpacity: 0.2,
          shadowRadius: 12,
          shadowOffset: { width: 0, height: 4 },
          elevation: 6,
        }}
      >
        {syncing ? (
          <Animated.View style={{ transform: [{ rotate }] }}>
            <Icon name={iconName} size={20} color={iconColor} />
          </Animated.View>
        ) : (
          <Icon name={iconName} size={20} color={iconColor} />
        )}
        <View style={{ flex: 1 }}>
          <Text variant="caption" weight="semibold" style={{ color: "#FFFFFF" }}>
            {title}
          </Text>
          <Text variant="caption" style={{ color: "#E5E7EB", fontSize: 11 }}>
            {subtitle}
          </Text>
        </View>
      </View>
    </View>
  );
}

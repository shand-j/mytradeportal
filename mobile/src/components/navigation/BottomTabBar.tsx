import { Pressable, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter, usePathname } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Text } from "../ui/Text";
import { useTheme } from "../../theme/ThemeProvider";

type TabItem = {
  key: string;
  label: string;
  icon: keyof typeof Ionicons.glyphMap;
  path: string;
  testID: string;
};

const TRADE_TABS: TabItem[] = [
  { key: "dashboard", label: "Dashboard", icon: "home", path: "/(trade)/dashboard", testID: "tab-dashboard" },
  { key: "quotes", label: "Quotes", icon: "document-text", path: "/(trade)/quotes", testID: "tab-quotes" },
  { key: "customers", label: "Customers", icon: "people", path: "/(trade)/customers", testID: "tab-customers" },
  { key: "calendar", label: "Calendar", icon: "calendar", path: "/(trade)/calendar", testID: "tab-calendar" },
  { key: "messages", label: "Messages", icon: "chatbubble", path: "/(trade)/leads", testID: "tab-messages" },
];

const CUSTOMER_TABS: TabItem[] = [
  { key: "requests", label: "Quotes", icon: "document-text", path: "/(customer)/requests", testID: "tab-requests" },
  { key: "calendar", label: "Calendar", icon: "calendar", path: "/(customer)/calendar", testID: "tab-calendar" },
  { key: "messages", label: "Messages", icon: "chatbubble", path: "/(customer)/messages", testID: "tab-messages" },
  { key: "profile", label: "Profile", icon: "person", path: "/(customer)/profile", testID: "tab-profile" },
];

type BottomTabBarProps = {
  variant: "trade" | "customer";
};

export function BottomTabBar({ variant }: BottomTabBarProps) {
  const router = useRouter();
  const pathname = usePathname();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const tabs = variant === "trade" ? TRADE_TABS : CUSTOMER_TABS;

  return (
    <View
      className="flex-row border-t border-gray-200 bg-white pt-2"
      style={{ paddingBottom: insets.bottom + 8 }}
    >
      {tabs.map((tab) => {
        const isActive = pathname === tab.path;
        return (
          <Pressable
            key={tab.key}
            testID={tab.testID}
            onPress={() => router.replace(tab.path)}
            className="flex-1 items-center justify-center"
          >
            <Ionicons name={tab.icon} size={22} color={isActive ? colors.primary : "#6B7280"} />
            <Text
              variant="caption"
              color={isActive ? "primary" : "secondary"}
              weight={isActive ? "semibold" : "normal"}
            >
              {tab.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

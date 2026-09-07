import { ReactNode } from "react";
import { View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

export function Screen({ children, style, testID }: { children: ReactNode; style?: object; testID?: string }) {
  const { top, bottom } = useSafeAreaInsets();
  return (
    <View
      testID={testID}
      className="flex-1 bg-white px-5"
      style={[
        {
          paddingTop: top + 16,
          paddingBottom: bottom + 24,
        },
        style,
      ]}
    >
      {children}
    </View>
  );
}

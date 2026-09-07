import { ReactNode } from "react";
import { Pressable, View } from "react-native";
import { Icon } from "./Icon";
import { Text } from "./Text";

export type HeaderProps = {
  title: string;
  onBack?: () => void;
  rightAction?: ReactNode;
  testID?: string;
};

export function Header({ title, onBack, rightAction, testID }: HeaderProps) {
  return (
    <View
      className="mb-4 flex-row items-center justify-between"
      style={{ minHeight: 44 }}
      testID={testID}
    >
      <View className="w-24 items-start justify-center">
        {onBack ? (
          <Pressable
            testID="back-button"
            onPress={onBack}
            className="flex-row items-center gap-1 py-1 pr-2"
            hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
          >
            <Icon name="back" size={22} color="#374151" />
            <Text variant="body" weight="medium" color="secondary" style={{ fontSize: 16 }}>
              Back
            </Text>
          </Pressable>
        ) : null}
      </View>
      <View className="flex-1 items-center">
        <Text variant="subtitle" weight="bold" align="center" numberOfLines={1} style={{ fontSize: 18 }}>
          {title}
        </Text>
      </View>
      <View className="w-24 items-end justify-center">{rightAction}</View>
    </View>
  );
}

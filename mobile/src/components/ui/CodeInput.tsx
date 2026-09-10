import { useRef, useState } from "react";
import { NativeSyntheticEvent, Pressable, TextInput, TextInputKeyPressEventData, View, LayoutChangeEvent } from "react-native";

type CodeInputProps = {
  value: string;
  onChange: (value: string) => void;
  length?: number;
  disabled?: boolean;
};

const GAP = 8;
const MAX_BOX_WIDTH = 48;

export function CodeInput({ value, onChange, length = 6, disabled }: CodeInputProps) {
  const [focusedIndex, setFocusedIndex] = useState(0);
  const [containerWidth, setContainerWidth] = useState(0);
  const inputsRef = useRef<TextInput[]>([]);

  const setRef = (index: number) => (el: TextInput | null) => {
    if (el) inputsRef.current[index] = el;
  };

  const chars = value.split("").slice(0, length);
  while (chars.length < length) chars.push("");

  const boxWidth =
    containerWidth > 0
      ? Math.max(44, Math.min(MAX_BOX_WIDTH, (containerWidth - (length - 1) * GAP) / length))
      : MAX_BOX_WIDTH;

  const focus = (index: number) => {
    const input = inputsRef.current[index];
    if (input) input.focus();
    setFocusedIndex(index);
  };

  const handleChange = (text: string, index: number) => {
    const next = text.replace(/\D/g, "").slice(-1);
    const nextValue = value.slice(0, index) + next + value.slice(index + 1);
    onChange(nextValue.slice(0, length));
    if (next && index < length - 1) {
      focus(index + 1);
    }
  };

  const handleKeyPress = (e: NativeSyntheticEvent<TextInputKeyPressEventData>, index: number) => {
    if (e.nativeEvent.key === "Backspace") {
      if (chars[index]) {
        const nextValue = value.slice(0, index) + value.slice(index + 1);
        onChange(nextValue.slice(0, length));
      } else if (index > 0) {
        focus(index - 1);
      }
    }
  };

  return (
    <View className="w-full flex-row justify-center gap-2" onLayout={(e: LayoutChangeEvent) => setContainerWidth(e.nativeEvent.layout.width)}>
      {chars.map((char, index) => (
        <Pressable key={index} onPress={() => focus(index)} style={{ width: boxWidth, height: boxWidth }}>
          <TextInput
            testID={`business-code-${index}`}
            ref={setRef(index)}
            style={{
              width: boxWidth,
              height: boxWidth,
              borderRadius: 16,
              borderWidth: focusedIndex === index || char ? 2 : 1,
              borderColor: focusedIndex === index || char ? "#1B2A32" : "#E5E7EB",
              backgroundColor: char ? "#EFF6FF" : "#FFFFFF",
              fontSize: 26,
              fontWeight: "600",
              textAlign: "center",
              padding: 0,
            }}
            value={char}
            onChangeText={(text) => handleChange(text, index)}
            onKeyPress={(e) => handleKeyPress(e, index)}
            onFocus={() => setFocusedIndex(index)}
            maxLength={1}
            keyboardType="number-pad"
            selectTextOnFocus
            editable={!disabled}
            caretHidden
          />
        </Pressable>
      ))}
    </View>
  );
}

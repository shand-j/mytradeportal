import { TextInput, View } from "react-native";
import { Text } from "./Text";

export type FormFieldProps = {
  label: string;
  value: string;
  onChangeText: (text: string) => void;
  placeholder?: string;
  error?: string | null;
  helper?: string;
  keyboardType?:
    | "default"
    | "email-address"
    | "phone-pad"
    | "number-pad"
    | "decimal-pad";
  secureTextEntry?: boolean;
  autoCapitalize?: "none" | "sentences" | "words" | "characters";
  maxLength?: number;
  multiline?: boolean;
  testID?: string;
};

export function FormField({
  label,
  value,
  onChangeText,
  placeholder,
  error,
  helper,
  testID,
  secureTextEntry,
  ...inputProps
}: FormFieldProps) {
  return (
    <View className="gap-1">
      <Text variant="body" weight="semibold">
        {label}
      </Text>
      <TextInput
        testID={testID}
        className={`h-12 rounded-xl border bg-white px-4 text-base text-slate-900 ${
          error ? "border-red-500" : "border-slate-200"
        }`}
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor="#94A3B8"
        // Keep iOS strong-password autofill away from secure fields: tapping
        // into a filled password box would otherwise wipe it on the next key.
        {...(secureTextEntry ? { textContentType: "none" as const, autoComplete: "off" as const } : {})}
        secureTextEntry={secureTextEntry}
        {...inputProps}
      />
      {error ? (
        <Text variant="caption" color="warning">
          {error}
        </Text>
      ) : null}
      {helper ? (
        <Text variant="caption" color="secondary">
          {helper}
        </Text>
      ) : null}
    </View>
  );
}

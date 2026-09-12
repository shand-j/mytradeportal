import { useState } from "react";
import { Pressable, ScrollView, View } from "react-native";
import { Button } from "../../../components/ui/Button";
import { FormField } from "../../../components/ui/FormField";
import { Text } from "../../../components/ui/Text";

type AccountStepProps = {
  data?: Record<string, unknown>;
  onNext: (data?: Record<string, unknown>) => void;
};

const ROLES = [
  { key: "owner", label: "Owner" },
  { key: "admin", label: "Admin" },
  { key: "office_manager", label: "Office manager" },
  { key: "engineer", label: "Engineer" },
];

export function AccountStep({ data, onNext }: AccountStepProps) {
  const [fullName, setFullName] = useState((data?.fullName as string) ?? "");
  const [email, setEmail] = useState((data?.email as string) ?? "");
  const [phone, setPhone] = useState((data?.phone as string) ?? "");
  const [password, setPassword] = useState((data?.password as string) ?? "");
  const [role, setRole] = useState((data?.role as string) ?? "owner");
  const [termsAccepted, setTermsAccepted] = useState((data?.termsAccepted as boolean) ?? false);
  const [showPassword, setShowPassword] = useState(false);

  const canContinue = fullName.trim().length >= 2 && email.includes("@") && password.length >= 8 && termsAccepted;

  const strength = password.length === 0 ? 0 : password.length < 8 ? 1 : password.length < 12 ? 2 : 3;
  const strengthLabels = ["", "Weak", "Good", "Strong"];
  const strengthColors = ["bg-slate-200", "bg-danger-400", "bg-amber-400", "bg-success-500"];

  return (
    <ScrollView className="flex-1" keyboardShouldPersistTaps="handled">
      <View className="gap-4 pb-6">
        <Text variant="title" weight="bold">
          Create your account
        </Text>
        <Text variant="body" color="secondary">
          This is how you’ll log in to manage your business.
        </Text>

        <FormField label="Full name" value={fullName} onChangeText={setFullName} placeholder="Full name" />
        <FormField
          label="Work email"
          value={email}
          onChangeText={setEmail}
          placeholder="you@business.com"
          keyboardType="email-address"
          autoCapitalize="none"
        />
        <FormField
          label="Mobile"
          value={phone}
          onChangeText={setPhone}
          placeholder="07700 123 456"
          keyboardType="phone-pad"
        />

        <View className="gap-1">
          <FormField
            label="Password"
            value={password}
            onChangeText={setPassword}
            placeholder="At least 8 characters"
            secureTextEntry={!showPassword}
          />
          <View className="flex-row items-center gap-2">
            <View className="h-2 flex-1 rounded-full bg-slate-200">
              <View className={`h-2 rounded-full ${strengthColors[strength]}`} style={{ width: `${(strength / 3) * 100}%` }} />
            </View>
            <Text variant="caption" color="secondary">
              {strengthLabels[strength]}
            </Text>
          </View>
          <Pressable onPress={() => setShowPassword((prev) => !prev)}>
            <Text variant="caption" color="primary">
              {showPassword ? "Hide password" : "Show password"}
            </Text>
          </Pressable>
        </View>

        <Text variant="body" weight="semibold">
          Role in business
        </Text>
        <View className="flex-row flex-wrap gap-2">
          {ROLES.map((r) => (
            <Button
              key={r.key}
              title={r.label}
              variant={role === r.key ? "primary" : "outline"}
              onPress={() => setRole(r.key)}
            />
          ))}
        </View>
        {role !== "owner" && (
          <Text variant="caption" color="secondary">
            Only owners can complete billing and team settings. Ask the owner to finish setup, or switch to Owner.
          </Text>
        )}

        <Pressable
          onPress={() => setTermsAccepted((prev) => !prev)}
          className="flex-row items-start gap-3"
        >
          <View
            className={`h-6 w-6 rounded-md border ${termsAccepted ? "border-primary bg-primary" : "border-slate-300 bg-white"}`}
          />
          <Text variant="body" style={{ flex: 1 }}>
            I accept the Terms of Service and Privacy Notice.
          </Text>
        </Pressable>

        <Button
          title="Continue"
          onPress={() => onNext({ fullName, email, phone, password, role, termsAccepted })}
          disabled={!canContinue}
        />
      </View>
    </ScrollView>
  );
}

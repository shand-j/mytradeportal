import { useMemo, useState } from "react";
import { ActivityIndicator, ScrollView, View } from "react-native";
import { useRouter } from "expo-router";
import { Button } from "../../../components/ui/Button";
import { Text } from "../../../components/ui/Text";
import { FormField } from "../../../components/ui/FormField";
import { useBusiness } from "../../../theme/ThemeProvider";
import { useAuth } from "../../../contexts/AuthContext";
import { ApiError } from "../../../lib/apiClient";
import { StepPropsWithBusiness } from "./types";

export type AccountCreationStepProps = StepPropsWithBusiness & {
  /** The id of the quote request just submitted; linked to the new customer account. */
  quoteRequestId: string;
};

export function AccountCreationStep({
  formData,
  onNext,
  onBack,
  quoteRequestId,
}: AccountCreationStepProps) {
  const { business } = useBusiness();
  const { registerCustomerAccount } = useAuth();
  const router = useRouter();
  const [emailTaken, setEmailTaken] = useState(false);
  const businessName = business?.name ?? "Your electrician";

  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const contact = formData.contact;
  const customerEmail = contact.email || "";
  const customerPhone = contact.mobile || "";
  const customerName = contact.name || "";

  const passwordValid = useMemo(() => {
    if (password.length < 8) return false;
    if (password !== confirmPassword) return false;
    return true;
  }, [password, confirmPassword]);

  const handleCreateAccount = async () => {
    if (!passwordValid) {
      setError(password.length < 8 ? "Password must be at least 8 characters" : "Passwords do not match");
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      const ok = await registerCustomerAccount({
        fullName: customerName,
        email: customerEmail,
        phone: customerPhone,
        password,
        preferredContactMethod: contact.preferredContact,
        quoteRequestId,
      });
      if (ok) {
        onNext();
      } else {
        setError("Could not create account. Please check your details and try again.");
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setEmailTaken(true);
        setError("An account with this email already exists. Log in to continue.");
      } else {
        setError("Something went wrong. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ScrollView contentContainerClassName="gap-4 pb-6">
      <View className="rounded-2xl bg-indigo-50 p-4 gap-2">
        <Text variant="body" weight="semibold">
          Create your account
        </Text>
        <Text variant="caption" color="secondary">
          {businessName} needs a way to keep you updated. Set a password to track your quote and
          chat with {businessName}.
        </Text>
      </View>

      <View className="rounded-2xl bg-slate-100 p-4 gap-4">
        <View className="gap-1">
          <Text variant="body" weight="semibold">Name</Text>
          <Text variant="body">{customerName}</Text>
        </View>
        <View className="gap-1">
          <Text variant="body" weight="semibold">Email</Text>
          <Text variant="body">{customerEmail}</Text>
        </View>
        <View className="gap-1">
          <Text variant="body" weight="semibold">Phone</Text>
          <Text variant="body">{customerPhone}</Text>
        </View>
        <FormField
          label="Password"
          value={password}
          onChangeText={setPassword}
          placeholder="At least 8 characters"
          secureTextEntry
          autoCapitalize="none"
          testID="account-password"
        />
        <FormField
          label="Confirm password"
          value={confirmPassword}
          onChangeText={setConfirmPassword}
          placeholder="Re-enter your password"
          secureTextEntry
          autoCapitalize="none"
          testID="account-confirm-password"
        />
      </View>

      {error && (
        <View className="rounded-2xl bg-amber-50 p-4">
          <Text variant="caption" color="warning" align="center">
            {error}
          </Text>
        </View>
      )}

      {submitting ? (
        <ActivityIndicator />
      ) : emailTaken ? (
        <>
          <Button
            testID="account-login-instead"
            title="Log in instead"
            onPress={() => router.replace("/customer-login")}
          />
          <Button title="Back" variant="outline" onPress={onBack} />
        </>
      ) : (
        <>
          <Button testID="account-create" title="Create account & track my quote" onPress={handleCreateAccount} disabled={!passwordValid} />
          <Button title="Back" variant="outline" onPress={onBack} />
        </>
      )}
    </ScrollView>
  );
}

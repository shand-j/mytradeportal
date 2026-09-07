import { useMemo, useState } from "react";
import { StyleSheet, TextInput, View } from "react-native";
import { useRouter } from "expo-router";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { confirmPasswordReset } from "../../api/auth";
import { NetworkError } from "../../lib/apiClient";

export type ResetPasswordScreenProps = {
  token: string | null;
  onBack: () => void;
};

// Server enforces min 8; enforce 12 client-side to match the onboarding
// AccountStep for consistency and to avoid ping-pong.
const PASSWORD_MIN = 12;

export function ResetPasswordScreen({ token, onBack }: ResetPasswordScreenProps) {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  const canSubmit = useMemo(() => {
    if (!token) return false;
    return (
      password.length >= PASSWORD_MIN &&
      password === confirm &&
      !loading
    );
  }, [token, password, confirm, loading]);

  const handleSubmit = () => {
    if (!token || !canSubmit) return;
    setError(null);
    setLoading(true);
    void (async () => {
      try {
        await confirmPasswordReset(token, password);
        setDone(true);
      } catch (err) {
        if (err instanceof NetworkError) {
          setError("Can't reach the server. Check your connection and try again.");
        } else {
          // 400 covers both invalid and expired tokens; the server does not
          // distinguish them so the user needs to request a new link.
          setError(
            "This reset link is invalid or has expired. Request a new one from the login screen."
          );
        }
      } finally {
        setLoading(false);
      }
    })();
  };

  if (!token) {
    return (
      <Screen>
        <Header title="Reset password" onBack={onBack} />
        <View style={styles.container}>
          <Text variant="title" weight="bold">
            Missing reset token
          </Text>
          <Text variant="body" color="secondary">
            Open the reset link from the email we sent you.
          </Text>
          <Button
            testID="reset-back-to-login"
            title="Back to sign in"
            onPress={() => router.replace("/")}
          />
        </View>
      </Screen>
    );
  }

  if (done) {
    return (
      <Screen>
        <Header title="Password updated" onBack={onBack} />
        <View style={styles.container}>
          <Text variant="title" weight="bold">
            All set
          </Text>
          <Text variant="body" color="secondary">
            Your password has been updated. Sign in with your new password.
          </Text>
          <Button
            testID="reset-back-to-login"
            title="Sign in"
            onPress={() => router.replace("/")}
          />
        </View>
      </Screen>
    );
  }

  return (
    <Screen>
      <Header title="Set a new password" onBack={onBack} />
      <View style={styles.container}>
        <Text variant="body" color="secondary">
          Enter a new password for your account. Minimum {PASSWORD_MIN} characters.
        </Text>
        <TextInput
          testID="reset-new-password"
          style={styles.input}
          value={password}
          onChangeText={setPassword}
          placeholder="New password"
          secureTextEntry
          autoCapitalize="none"
        />
        <TextInput
          testID="reset-confirm-password"
          style={styles.input}
          value={confirm}
          onChangeText={setConfirm}
          placeholder="Confirm new password"
          secureTextEntry
          autoCapitalize="none"
        />
        {password.length > 0 && password.length < PASSWORD_MIN && (
          <Text testID="reset-hint-too-short" variant="caption" color="secondary">
            Password must be at least {PASSWORD_MIN} characters.
          </Text>
        )}
        {password.length >= PASSWORD_MIN && confirm.length > 0 && password !== confirm && (
          <Text testID="reset-hint-mismatch" variant="caption" color="warning">
            The passwords don't match.
          </Text>
        )}
        {error && (
          <Text testID="reset-error" variant="caption" color="warning">
            {error}
          </Text>
        )}
        <Button
          testID="reset-submit"
          title={loading ? "Updating…" : "Update password"}
          onPress={handleSubmit}
          disabled={!canSubmit}
        />
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    paddingVertical: 24,
    gap: 16,
  },
  input: {
    height: 48,
    borderRadius: 12,
    backgroundColor: "#F3F4F6",
    paddingHorizontal: 16,
  },
});

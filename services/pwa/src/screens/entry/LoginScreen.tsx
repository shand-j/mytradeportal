import { useState } from "react";
import { StyleSheet, TextInput, View } from "react-native";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { useAuth } from "../../contexts/AuthContext";
import { AppRole } from "../../types";

export type LoginScreenMode = "login" | "register";

export type LoginScreenProps = {
  role: AppRole;
  mode?: LoginScreenMode;
  onBack: () => void;
};

export function LoginScreen({ role, mode = "login", onBack }: LoginScreenProps) {
  const { login, registerCustomerAccount } = useAuth();
  const [currentMode, setCurrentMode] = useState<LoginScreenMode>(mode);
  const [email, setEmail] = useState(role === "trade" ? "owner@demo.trade" : "jane@example.com");
  const [password, setPassword] = useState("demo123");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const isRegister = currentMode === "register";

  const handleSubmit = () => {
    setError(null);
    setLoading(true);
    void (async () => {
      try {
        const ok = isRegister
          ? await registerCustomerAccount({ fullName: name, email, phone, password })
          : await login(email, password, role);
        if (!ok) {
          setError(
            isRegister
              ? "We couldn't create your account. That email may already be registered."
              : "Invalid email or password. Try the demo credentials."
          );
        }
      } catch {
        setError("Something went wrong. Please try again.");
      } finally {
        setLoading(false);
      }
    })();
  };

  const title =
    role === "trade" ? "Electrician login" : isRegister ? "Create your account" : "Customer login";
  const subtitle =
    role === "trade"
      ? "Access your leads, quotes and calendar."
      : isRegister
        ? "Set up your account so you can track your quotes."
        : "Track your quote requests and messages.";
  const submitLabel = isRegister
    ? loading
      ? "Creating account…"
      : "Create account"
    : loading
      ? "Signing in…"
      : "Sign in";

  const canSubmit =
    email &&
    password &&
    (!isRegister || (name.trim() && phone.trim() && password.length >= 8));

  return (
    <Screen style={styles.container}>
      <Header title={title} onBack={onBack} />
      <Text variant="body" color="secondary">
        {subtitle}
      </Text>

      <View style={styles.card}>
        {isRegister && role === "customer" && (
          <>
            <TextInput testID="login-name" style={styles.input} value={name} onChangeText={setName} placeholder="Full name" />
            <TextInput testID="login-phone" style={styles.input} value={phone} onChangeText={setPhone} placeholder="Phone" keyboardType="phone-pad" />
          </>
        )}
        <TextInput
          testID="login-email"
          style={styles.input}
          value={email}
          onChangeText={setEmail}
          placeholder="Email"
          autoCapitalize="none"
          keyboardType="email-address"
        />
        <TextInput
          testID="login-password"
          style={styles.input}
          value={password}
          onChangeText={setPassword}
          placeholder={isRegister ? "Password (min 8 characters)" : "Password"}
          secureTextEntry
        />
        {error && (
          <Text testID="login-error" variant="caption" color="warning">
            {error}
          </Text>
        )}
        <Button testID="login-submit" title={submitLabel} onPress={handleSubmit} disabled={!canSubmit} />
        {!isRegister && <Button title="Forgot password?" variant="ghost" onPress={() => {}} />}
        {role === "customer" && (
          <Button
            testID="login-toggle-mode"
            title={isRegister ? "I already have an account" : "Create an account"}
            variant="ghost"
            onPress={() => {
              setError(null);
              setCurrentMode(isRegister ? "login" : "register");
            }}
          />
        )}
      </View>

      {!isRegister && (
        <View style={styles.hint}>
          <Text variant="caption" color="secondary">
            Demo: {role === "trade" ? "owner@demo.trade" : "jane@example.com"} / demo123
          </Text>
        </View>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  container: {
    paddingVertical: 24,
    gap: 16,
  },
  card: {
    padding: 20,
    borderRadius: 16,
    backgroundColor: "#F3F4F6",
    gap: 12,
  },
  input: {
    height: 48,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#E5E7EB",
    backgroundColor: "#FFFFFF",
    paddingHorizontal: 16,
    fontSize: 16,
  },
  hint: {
    alignItems: "center",
  },
});

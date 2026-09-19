import { useEffect, useState } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, TextInput, View } from "react-native";
import { useRouter } from "expo-router";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { requestPasswordReset } from "../../api/auth";
import { requestInviteMagicLink } from "../../api/users";
import { useAuth } from "../../contexts/AuthContext";
import { NetworkError } from "../../lib/apiClient";
import { pendingInviteStorage } from "../../lib/pendingInvite";
import { useBusiness } from "../../theme/ThemeProvider";
import { AppRole } from "../../types";

export type LoginScreenMode = "login" | "register";

export type LoginScreenProps = {
  role: AppRole;
  mode?: LoginScreenMode;
  /** Pre-fill the email field (e.g. when sent here from onboarding after a
   * duplicate-account conflict). */
  initialEmail?: string;
  onBack: () => void;
};

const PREFERRED_CONTACT_OPTIONS = [
  { key: "in_app_chat", label: "In-app chat" },
  { key: "phone", label: "Phone" },
  { key: "sms", label: "SMS" },
  { key: "whatsapp", label: "WhatsApp" },
  { key: "email", label: "Email" },
];

export function LoginScreen({ role, mode = "login", initialEmail, onBack }: LoginScreenProps) {
  const { login, registerCustomerAccount } = useAuth();
  const { business } = useBusiness();
  const router = useRouter();
  const [currentMode, setCurrentMode] = useState<LoginScreenMode>(mode);
  const [email, setEmail] = useState(initialEmail ?? "");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");
  const [preferredContact, setPreferredContact] = useState("in_app_chat");
  const [marketingConsent, setMarketingConsent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [resetRequested, setResetRequested] = useState(false);
  const [resetLoading, setResetLoading] = useState(false);
  const [inviteLinkRequested, setInviteLinkRequested] = useState(false);
  const [inviteLinkLoading, setInviteLinkLoading] = useState(false);
  // Set when the email field was pre-filled from a pending invite — prompts
  // the invitee to set their password from the email, then log in here.
  const [invitePrefilled, setInvitePrefilled] = useState(false);

  const isRegister = currentMode === "register";

  // Trade login: pre-fill the email a pending invitee typed when they asked
  // for their invite link, so after setting a password (landing page) they
  // land back here ready to sign in.
  useEffect(() => {
    if (role !== "trade") return;
    void pendingInviteStorage.getEmail().then((saved) => {
      if (saved) {
        setEmail((current) => current || saved);
        setInvitePrefilled(true);
      }
    });
  }, [role]);

  const handleForgotPassword = () => {
    setError(null);
    if (!email.trim()) {
      setError("Enter your email above so we know where to send the reset link.");
      return;
    }
    setResetLoading(true);
    void (async () => {
      try {
        await requestPasswordReset(email.trim());
        setResetRequested(true);
      } catch (err) {
        // The API returns a generic response, so a thrown error here means
        // the network call itself failed rather than the account not
        // existing — the generic status message is still safe to show.
        setError(
          err instanceof NetworkError
            ? "Can't reach the server. Check your connection and try again."
            : "Something went wrong. Please try again."
        );
      } finally {
        setResetLoading(false);
      }
    })();
  };

  const handleInviteLink = () => {
    setError(null);
    if (!email.trim()) {
      setError("Enter your invited email above so we know where to send your link.");
      return;
    }
    setInviteLinkLoading(true);
    void (async () => {
      try {
        await requestInviteMagicLink(email.trim());
        await pendingInviteStorage.saveEmail(email.trim());
        setInviteLinkRequested(true);
        setInvitePrefilled(true);
      } catch (err) {
        // The API answers generically, so a thrown error is a transport
        // problem, not an unknown email.
        setError(
          err instanceof NetworkError
            ? "Can't reach the server. Check your connection and try again."
            : "Something went wrong. Please try again."
        );
      } finally {
        setInviteLinkLoading(false);
      }
    })();
  };

  const handleSubmit = () => {
    setError(null);
    setLoading(true);
    void (async () => {
      try {
        const ok = isRegister
          ? await registerCustomerAccount({
              fullName: name,
              email,
              phone,
              password,
              address: address || undefined,
              preferredContactMethod: preferredContact,
              marketingConsent,
            })
          : await login(email, password, role);
        if (ok) {
          void pendingInviteStorage.clear();
          // The auth-guard redirect lives on the index route, which is not
          // mounted here — navigate explicitly on success.
          router.replace(role === "trade" ? "/(trade)/dashboard" : "/(customer)/requests");
          return;
        }
        setError(
          isRegister
            ? "We couldn't create your account. That email may already be registered."
            : "Invalid email or password."
        );
      } catch (err) {
        if (err instanceof NetworkError) {
          setError("Can't reach the server. Check your connection and try again.");
        } else {
          setError("Something went wrong. Please try again.");
        }
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

  // Login is tenant-agnostic (the account is located by email); only
  // registration still targets a specific business.
  const showNoBusinessWarning = !business && role !== "trade" && isRegister;

  return (
    <Screen style={styles.container}>
      <Header title={title} onBack={onBack} />
      <Text variant="body" color="secondary">
        {subtitle}
      </Text>

      {showNoBusinessWarning && (
        <Text variant="caption" color="warning">
          Choose a business on the previous screen first so we know where to send your request.
        </Text>
      )}

      <KeyboardAvoidingView
        style={styles.keyboardAvoider}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <ScrollView style={styles.scroll} contentContainerStyle={styles.card} keyboardShouldPersistTaps="handled">
        {isRegister && role === "customer" && (
          <>
            <TextInput testID="login-name" style={styles.input} value={name} onChangeText={setName} placeholder="Full name" />
            <TextInput testID="login-phone" style={styles.input} value={phone} onChangeText={setPhone} placeholder="Phone" keyboardType="phone-pad" />
            <TextInput
              testID="login-address"
              style={[styles.input, styles.multiline]}
              value={address}
              onChangeText={setAddress}
              placeholder="Address"
              multiline
              numberOfLines={2}
            />
            <View style={styles.contactOptions}>
              <Text variant="caption" color="secondary">Preferred contact</Text>
              <View style={styles.contactChips}>
                {PREFERRED_CONTACT_OPTIONS.map((option) => (
                  <View key={option.key} style={styles.chipWrapper}>
                    <Button
                      testID={`login-contact-${option.key}`}
                      title={option.label}
                      size="sm"
                      variant={preferredContact === option.key ? "primary" : "outline"}
                      onPress={() => setPreferredContact(option.key)}
                    />
                  </View>
                ))}
              </View>
            </View>
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
        {isRegister && role === "customer" && (
          <Button
            testID="login-marketing-consent"
            title={marketingConsent ? "✓ Marketing updates accepted" : "Receive marketing updates"}
            variant={marketingConsent ? "primary" : "ghost"}
            size="sm"
            onPress={() => setMarketingConsent((v) => !v)}
          />
        )}
        {error && (
          <Text testID="login-error" variant="caption" color="warning">
            {error}
          </Text>
        )}
        <Button testID="login-submit" title={submitLabel} onPress={handleSubmit} disabled={!canSubmit} />
        {!isRegister && !resetRequested && (
          <Button
            testID="login-forgot-password"
            title={resetLoading ? "Sending reset link…" : "Forgot password?"}
            variant="ghost"
            disabled={resetLoading}
            onPress={handleForgotPassword}
          />
        )}
        {resetRequested && (
          <Text testID="login-reset-sent" variant="caption" color="secondary">
            If an account exists for {email.trim()}, we've emailed a reset link. Check
            your inbox (and spam) — the link expires in 30 minutes.
          </Text>
        )}
        {role === "trade" && !isRegister && invitePrefilled && !inviteLinkRequested && (
          <Text testID="login-invite-prefilled" variant="caption" color="secondary">
            Set your password from the invite email we sent you, then log in below.
          </Text>
        )}
        {role === "trade" && !isRegister && !inviteLinkRequested && (
          <Button
            testID="login-invite-link"
            title={inviteLinkLoading ? "Sending your link…" : "Been invited? Get your sign-in link"}
            variant="ghost"
            disabled={inviteLinkLoading}
            onPress={handleInviteLink}
          />
        )}
        {inviteLinkRequested && (
          <Text testID="login-invite-sent" variant="caption" color="secondary">
            If {email.trim()} has a pending invite, we've emailed a link to set your
            password. Follow it, then log in here.
          </Text>
        )}
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
        </ScrollView>
      </KeyboardAvoidingView>

    </Screen>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    paddingVertical: 24,
    gap: 16,
  },
  scroll: {
    flex: 1,
  },
  keyboardAvoider: {
    flex: 1,
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
  multiline: {
    height: 72,
    paddingTop: 12,
    textAlignVertical: "top",
  },
  contactOptions: {
    gap: 8,
  },
  contactChips: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  chipWrapper: {
    flexGrow: 0,
  },
});

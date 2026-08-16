import { useState } from "react";
import { StyleSheet, View } from "react-native";
import { Button } from "../../components/ui/Button";
import { CodeInput } from "../../components/ui/CodeInput";
import { Header } from "../../components/ui/Header";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { useAuth } from "../../contexts/AuthContext";
import { lookupMockBusiness } from "../../data/mockBusinesses";
import { useBusiness } from "../../theme/ThemeProvider";
import { AppRole } from "../../types";
import { CustomerQuoteRequestFlow } from "../customer/CustomerQuoteRequestFlow";
import { LoginScreen } from "./LoginScreen";

export function EntryScreen() {
  const { startRegistration, setUser, setRole, completeOnboarding } = useAuth();
  const { business, setBusiness } = useBusiness();
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loginRole, setLoginRole] = useState<AppRole | null>(null);
  const [requestingQuote, setRequestingQuote] = useState(false);

  const lookupBusiness = () => {
    setError(null);
    const config = lookupMockBusiness(code);
    if (config) {
      setBusiness(config);
    } else {
      setError("We couldn't find a business with that code. Try '123456' or '654321'.");
    }
  };

  const clearBusiness = () => {
    setBusiness(null);
    setCode("");
    setError(null);
  };

  const handleQuoteComplete = () => {
    setUser({ id: "demo-customer", email: "jane@example.com", fullName: "Jane Homeowner", role: "owner" });
    setRole("customer");
    completeOnboarding();
  };

  if (requestingQuote) {
    return (
      <CustomerQuoteRequestFlow
        onClose={handleQuoteComplete}
        onCancel={() => setRequestingQuote(false)}
      />
    );
  }

  if (loginRole) {
    return <LoginScreen role={loginRole} onBack={() => setLoginRole(null)} />;
  }

  return (
    <Screen>
      {business ? (
        <>
          <Header title="Your electrician" onBack={clearBusiness} />
          <View style={styles.businessCard}>
            <Text variant="title" weight="bold" align="center">
              {business.name}
            </Text>
            <Text variant="body" color="secondary" align="center">
              {business.address || "Serving your area"}
            </Text>
            <View style={styles.actions}>
              <Button testID="entry-request-quote" title="Request a quote" onPress={() => setRequestingQuote(true)} />
              <Button
                testID="entry-customer-login"
                title="Customer login"
                variant="outline"
                onPress={() => setLoginRole("customer")}
              />
            </View>
          </View>
        </>
      ) : (
        <View style={styles.container}>
          <Text variant="title" weight="bold" align="center">
            My Trade Portal
          </Text>
          <Text variant="subtitle" color="secondary" align="center">
            Find your local electrician and request a quote.
          </Text>

          <View style={[styles.card, styles.codeCard]}>
            <Text variant="body" weight="semibold" align="center">
              Enter your electrician's 6-digit code
            </Text>
            <CodeInput value={code} onChange={setCode} />
            {error && (
              <Text variant="caption" color="warning" align="center">
                {error}
              </Text>
            )}
            <Button testID="entry-find-business" title="Find my electrician" onPress={lookupBusiness} disabled={code.trim().length !== 6} />
          </View>

          <View style={styles.divider} />

          <View style={styles.card}>
            <Button testID="entry-register-trade" title="Register my business" onPress={() => startRegistration("trade")} />
            <Button testID="entry-trade-login" title="Electrician login" variant="ghost" onPress={() => setLoginRole("trade")} />
            <Button testID="entry-customer-login" title="Customer login" variant="outline" onPress={() => setLoginRole("customer")} />
          </View>
        </View>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: "center",
    gap: 16,
  },
  card: {
    padding: 20,
    borderRadius: 16,
    backgroundColor: "#F3F4F6",
    gap: 12,
  },
  codeCard: {
    paddingHorizontal: 12,
  },
  businessCard: {
    padding: 28,
    borderRadius: 20,
    backgroundColor: "#FFFFFF",
    borderWidth: 1,
    borderColor: "#E5E7EB",
    gap: 16,
    marginTop: 8,
  },
  actions: {
    gap: 12,
  },
  divider: {
    height: 1,
    backgroundColor: "#E5E7EB",
    marginVertical: 8,
  },
});

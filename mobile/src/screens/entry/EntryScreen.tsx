import { useEffect, useRef, useState } from "react";
import {
  AccessibilityInfo,
  ActivityIndicator,
  Animated,
  Image,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  View,
} from "react-native";
import mtMark from "../../../assets/icon.png";
import { Button } from "../../components/ui/Button";
import { CodeInput } from "../../components/ui/CodeInput";
import { Header } from "../../components/ui/Header";
import { Icon } from "../../components/ui/Icon";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { useAuth } from "../../contexts/AuthContext";
import { useBusiness } from "../../theme/ThemeProvider";
import { AppRole } from "../../types";
import { CustomerQuoteRequestFlow } from "../customer/CustomerQuoteRequestFlow";
import { LoginScreen } from "./LoginScreen";

// The animated splash plays once per app session (first cold open).
// Re-entering the entry screen — e.g. after logout — goes straight to content.
let splashConsumedThisSession = false;

const SPLASH_DURATION_MS = 1800;

type EntryView = "role" | "electrician" | "customer";

export function EntryScreen() {
  const { startRegistration } = useAuth();
  const { business, theme, isLoading, error, loadBusiness, clearBusiness } = useBusiness();
  const [code, setCode] = useState("");
  const [loginRole, setLoginRole] = useState<AppRole | null>(null);
  const [requestingQuote, setRequestingQuote] = useState(false);
  const [view, setView] = useState<EntryView>("role");

  const [showSplash, setShowSplash] = useState(!splashConsumedThisSession);
  const [reduceMotion, setReduceMotion] = useState(false);
  const logoOpacity = useRef(new Animated.Value(0)).current;
  const logoScale = useRef(new Animated.Value(0.55)).current;
  const contentOpacity = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    AccessibilityInfo.isReduceMotionEnabled().then(setReduceMotion);
  }, []);

  useEffect(() => {
    if (!showSplash) return;
    const duration = reduceMotion ? 0 : 550;
    Animated.parallel([
      Animated.timing(logoOpacity, { toValue: 1, duration, useNativeDriver: true }),
      Animated.spring(logoScale, {
        toValue: 1,
        friction: 7,
        tension: 60,
        useNativeDriver: true,
      }),
    ]).start();
    const timer = setTimeout(
      () => {
        splashConsumedThisSession = true;
        setShowSplash(false);
      },
      reduceMotion ? 400 : SPLASH_DURATION_MS,
    );
    return () => clearTimeout(timer);
  }, [showSplash, reduceMotion, logoOpacity, logoScale]);

  useEffect(() => {
    if (showSplash) return;
    Animated.timing(contentOpacity, {
      toValue: 1,
      duration: reduceMotion ? 0 : 320,
      useNativeDriver: true,
    }).start();
  }, [showSplash, reduceMotion, contentOpacity]);

  const lookupBusiness = () => {
    void loadBusiness(code);
  };

  if (requestingQuote) {
    return (
      <CustomerQuoteRequestFlow
        onClose={() => setRequestingQuote(false)}
        onCancel={() => setRequestingQuote(false)}
      />
    );
  }

  if (loginRole) {
    return <LoginScreen role={loginRole} onBack={() => setLoginRole(null)} />;
  }

  if (showSplash) {
    return (
      <View style={styles.splash} testID="splash">
        <Animated.Image
          source={mtMark}
          style={[
            styles.splashMark,
            { opacity: logoOpacity, transform: [{ scale: logoScale }] },
          ]}
          accessibilityLabel="My Trade Portal"
          resizeMode="cover"
        />
      </View>
    );
  }

  return (
    <Screen>
      <Animated.View style={[styles.flex, { opacity: contentOpacity }]}>
        {business ? (
          <>
            <Header title="Your electrician" onBack={clearBusiness} />
            <View style={[styles.businessCard, { borderColor: theme.colors.border }]}>
              {business.logoUrl ? (
                <Image source={{ uri: business.logoUrl }} style={styles.logo} resizeMode="contain" />
              ) : null}
              <Text variant="title" weight="bold" align="center" color="primary">
                {business.name}
              </Text>
              <Text variant="body" color="secondary" align="center">
                {business.address || "Serving your area"}
              </Text>
              {business.contactPhone ? (
                <Text variant="caption" color="secondary" align="center">
                  {business.contactPhone}
                </Text>
              ) : null}
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
        ) : view === "role" ? (
          <View style={styles.container} testID="role-select">
            <Image source={mtMark} style={styles.brandMarkSmall} accessibilityLabel="My Trade Portal" />
            <Text variant="title" weight="bold" align="center">
              Get started
            </Text>
            <Text variant="subtitle" color="secondary" align="center">
              Quotes, jobs and invoices — whichever side of the job you&apos;re on.
            </Text>

            <View style={styles.roleCards}>
              <RoleCard
                testID="role-electrician"
                icon="flash"
                title="I'm an Electrician"
                subtitle="Log in or register your business"
                onPress={() => setView("electrician")}
              />
              <RoleCard
                testID="role-customer"
                icon="profile"
                title="I'm a Customer"
                subtitle="Find your electrician or log in"
                onPress={() => setView("customer")}
              />
            </View>
          </View>
        ) : view === "electrician" ? (
          <>
            <Header title="Electrician" onBack={() => setView("role")} />
            <View style={styles.container}>
              <Image source={mtMark} style={styles.brandMarkSmall} accessibilityLabel="My Trade Portal" />
              <View style={styles.card}>
                <Button testID="entry-trade-login" title="Log in" onPress={() => setLoginRole("trade")} />
                <Button
                  testID="entry-register-trade"
                  title="Register my business"
                  variant="outline"
                  onPress={() => startRegistration("trade")}
                />
                <Text variant="caption" color="secondary" align="center">
                  Free during beta — no card required
                </Text>
              </View>
            </View>
          </>
        ) : (
          <>
            <Header title="Customer" onBack={() => setView("role")} />
            <KeyboardAvoidingView
              style={styles.flex}
              behavior={Platform.OS === "ios" ? "padding" : undefined}
            >
              <View style={styles.container}>
              <Image source={mtMark} style={styles.brandMarkSmall} accessibilityLabel="My Trade Portal" />
              <View style={[styles.card, styles.codeCard]}>
                <Text variant="body" weight="semibold" align="center">
                  Enter your electrician&apos;s code or business slug
                </Text>
                <CodeInput value={code} onChange={setCode} />
                {isLoading ? (
                  <ActivityIndicator color={theme.colors.primary} />
                ) : (
                  <Button
                    testID="entry-find-business"
                    title="Find my electrician"
                    onPress={lookupBusiness}
                    disabled={code.trim().length === 0}
                  />
                )}
                {error && (
                  <Text variant="caption" color="warning" align="center">
                    {error}
                  </Text>
                )}
              </View>

              <View style={styles.divider} />

              <View style={styles.card}>
                <Button
                  testID="entry-customer-login"
                  title="Customer login"
                  variant="outline"
                  onPress={() => setLoginRole("customer")}
                />
              </View>
              </View>
            </KeyboardAvoidingView>
          </>
        )}
      </Animated.View>
    </Screen>
  );
}

/* Chevron that points forward without adding a new icon mapping. */
function ChevronForward() {
  return (
    <View style={{ transform: [{ rotate: "180deg" }] }}>
      <Icon name="back" size={20} color="#6B7280" />
    </View>
  );
}

interface RoleCardProps {
  testID: string;
  icon: "flash" | "profile";
  title: string;
  subtitle: string;
  onPress: () => void;
}

function RoleCard({ testID, icon, title, subtitle, onPress }: RoleCardProps) {
  // Static styles on the Pressable's inner content View — function-style
  // Pressable styles break text rendering under RN 0.86 + NativeWind interop.
  const [pressed, setPressed] = useState(false);
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      onPressIn={() => setPressed(true)}
      onPressOut={() => setPressed(false)}
      accessibilityRole="button"
    >
      <View style={[styles.roleCard, pressed && styles.roleCardPressed]}>
        <View style={styles.roleIcon}>
          <Icon name={icon} size={28} color="#0F1E26" />
        </View>
        <View style={styles.roleCopy}>
          <Text variant="title" weight="bold">
            {title}
          </Text>
          <Text variant="body" color="secondary">
            {subtitle}
          </Text>
        </View>
        <ChevronForward />
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
  },
  splash: {
    flex: 1,
    backgroundColor: "#0F1E26",
    alignItems: "center",
    justifyContent: "center",
  },
  splashMark: {
    width: 128,
    height: 128,
    borderRadius: 28,
  },
  container: {
    flex: 1,
    justifyContent: "center",
    gap: 16,
  },
  brandMarkSmall: {
    width: 56,
    height: 56,
    alignSelf: "center",
    borderRadius: 14,
  },
  roleCards: {
    gap: 12,
    marginTop: 8,
  },
  roleCard: {
    flexDirection: "row",
    alignItems: "center",
    gap: 16,
    padding: 20,
    borderRadius: 16,
    backgroundColor: "#FFFFFF",
    borderWidth: 1,
    borderColor: "#E5E7EB",
  },
  roleCardPressed: {
    opacity: 0.7,
    backgroundColor: "#F3F4F6",
  },
  roleIcon: {
    width: 52,
    height: 52,
    borderRadius: 14,
    backgroundColor: "#FFC107",
    alignItems: "center",
    justifyContent: "center",
  },
  roleCopy: {
    flex: 1,
    gap: 2,
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
  logo: {
    width: 120,
    height: 60,
    alignSelf: "center",
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

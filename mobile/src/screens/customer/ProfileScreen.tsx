import { useEffect, useState } from "react";
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, TextInput, View } from "react-native";
import { useRouter } from "expo-router";
import { Button } from "../../components/ui/Button";
import { FormField } from "../../components/ui/FormField";
import { Header } from "../../components/ui/Header";
import { Icon } from "../../components/ui/Icon";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { useCustomerMe } from "../../api/auth";
import { useMyRequests } from "../../api/quoteRequests";
import { useAuth } from "../../contexts/AuthContext";
import { useBusiness } from "../../theme/ThemeProvider";

const CONTACT_METHODS = [
  { key: "in_app_chat", label: "Online chat", icon: "message" as const },
  { key: "phone", label: "Phone call", icon: "phone" as const },
  { key: "email", label: "Email", icon: "message" as const },
] as const;

type ContactMethod = (typeof CONTACT_METHODS)[number]["key"];

function Toggle({
  label,
  value,
  onChange,
}: {
  label: string;
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <Pressable onPress={() => onChange(!value)}>
      <View className="flex-row items-center justify-between py-1">
        <Text variant="body">{label}</Text>
        <View
          className="h-7 w-12 justify-center rounded-full px-0.5"
          style={{ backgroundColor: value ? "#2563EB" : "#E5E7EB" }}
        >
          <View
            className="h-6 w-6 rounded-full bg-white"
            style={{ transform: [{ translateX: value ? 20 : 0 }] }}
          />
        </View>
      </View>
    </Pressable>
  );
}

export type ProfileScreenProps = {
  navigation: {
    navigate: (name: string, params?: Record<string, unknown>) => void;
  };
};

export function ProfileScreen({ navigation }: ProfileScreenProps) {
  const router = useRouter();
  const { user, logout } = useAuth();
  const { business, setBusiness } = useBusiness();
  const { customer, isLoading: customerLoading } = useCustomerMe();
  const { requests } = useMyRequests();

  const [fullName, setFullName] = useState(user?.fullName ?? "");
  const [email, setEmail] = useState(user?.email ?? "");
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");
  const [preferredContact, setPreferredContact] = useState<ContactMethod>("email");
  const [emailQuotes, setEmailQuotes] = useState(true);
  const [smsReminders, setSmsReminders] = useState(true);
  const [saved, setSaved] = useState(false);

  // Pre-fill from the real customer record (GET /customer/me) once it lands —
  // the auth store only carries name/email from the login response.
  useEffect(() => {
    if (!customer) return;
    setFullName(customer.fullName ?? "");
    setEmail(customer.email ?? "");
    setPhone(customer.phone ?? "");
    const method = customer.preferredContactMethod as ContactMethod | undefined;
    if (method && CONTACT_METHODS.some((m) => m.key === method)) {
      setPreferredContact(method);
    }
  }, [customer]);

  const save = () => {
    // TODO: persist profile changes via the backend API.
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const handleBack = () => {
    if (router.canGoBack()) {
      router.back();
    } else {
      router.replace("/(customer)/requests");
    }
  };

  return (
    <Screen>
      <Header title="Profile" onBack={handleBack} />

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <ScrollView
          className="flex-1"
          contentContainerStyle={{ gap: 16, paddingBottom: 40 }}
          keyboardShouldPersistTaps="handled"
        >
        <Text variant="body" color="secondary">
          Your contact details, properties, and preferences for{" "}
          {business?.name ?? "your electrician"}.
        </Text>

        <View className="gap-1 rounded-2xl border border-slate-200 bg-white p-4">
          <Text variant="body" weight="semibold">
            {customerLoading
              ? "Loading your account…"
              : `${requests.length} quote request${requests.length === 1 ? "" : "s"}`}
          </Text>
          {!customerLoading && (
            <Text variant="caption" color="secondary">
              Submitted to {business?.name ?? "your electrician"} via your account.
            </Text>
          )}
        </View>

        <View className="gap-3 rounded-2xl border border-slate-200 bg-white p-4">
          <Text variant="body" weight="semibold">
            Personal details
          </Text>
          <FormField label="Full name" value={fullName} onChangeText={setFullName} placeholder="Full name" />
          <FormField
            label="Email"
            value={email}
            onChangeText={setEmail}
            placeholder="Email"
            keyboardType="email-address"
            autoCapitalize="none"
          />
          <FormField
            label="Phone"
            value={phone}
            onChangeText={setPhone}
            placeholder="Phone"
            keyboardType="phone-pad"
          />
        </View>

        <View className="gap-3 rounded-2xl border border-slate-200 bg-white p-4">
          <Text variant="body" weight="semibold">
            Address
          </Text>
          <TextInput
            className="min-h-20 rounded-xl border border-slate-200 bg-slate-50 p-3 text-base text-slate-900"
            value={address}
            onChangeText={setAddress}
            placeholder="Primary address"
            multiline
            numberOfLines={3}
          />
          <Text variant="caption" color="secondary">
            You can add more properties from your electrician's portal.
          </Text>
        </View>

        <View className="gap-3 rounded-2xl border border-slate-200 bg-white p-4">
          <Text variant="body" weight="semibold">
            Preferred contact method
          </Text>
          <View className="flex-row flex-wrap gap-2">
            {CONTACT_METHODS.map((method) => {
              const active = preferredContact === method.key;
              return (
                <Pressable
                  key={method.key}
                  onPress={() => setPreferredContact(method.key)}
                  className="flex-row items-center gap-1 rounded-xl border px-3 py-2"
                  style={{
                    backgroundColor: active ? "#EFF6FF" : "#F8FAFC",
                    borderColor: active ? "#2563EB" : "#E2E8F0",
                  }}
                >
                  <Icon name={method.icon} size={16} color={active ? "#2563EB" : "#6B7280"} />
                  <Text
                    variant="caption"
                    weight={active ? "semibold" : "normal"}
                    color={active ? "primary" : "secondary"}
                  >
                    {method.label}
                  </Text>
                </Pressable>
              );
            })}
          </View>
        </View>

        <View className="gap-3 rounded-2xl border border-slate-200 bg-white p-4">
          <Text variant="body" weight="semibold">
            Notifications
          </Text>
          <Toggle
            label="Email quotes and booking confirmations"
            value={emailQuotes}
            onChange={setEmailQuotes}
          />
          <Toggle label="SMS reminders for upcoming jobs" value={smsReminders} onChange={setSmsReminders} />
        </View>

        <View className="gap-3 rounded-2xl border border-slate-200 bg-white p-4">
          <Text variant="body" weight="semibold">
            Security
          </Text>
          <Button title="Change password" variant="outline" onPress={() => {}} />
        </View>

        {saved && (
          <View className="rounded-xl bg-green-50 p-3">
            <Text variant="body" color="success" align="center">
              Changes saved
            </Text>
          </View>
        )}

        <Button title="Save changes" onPress={save} />
        <Button
          title="Log out"
          variant="outline"
          onPress={() => {
            setBusiness(null);
            logout();
            navigation.navigate("Entry");
          }}
        />
        </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}

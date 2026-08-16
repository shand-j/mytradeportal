import { useState } from "react";
import { Pressable, ScrollView, TextInput, View } from "react-native";
import { Button } from "../../components/ui/Button";
import { FormField } from "../../components/ui/FormField";
import { Header } from "../../components/ui/Header";
import { Icon } from "../../components/ui/Icon";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { useAuth } from "../../contexts/AuthContext";
import { MOCK_CUSTOMERS } from "../../data/mockCustomers";
import { useBusiness } from "../../theme/ThemeProvider";

const CONTACT_METHODS = [
  { key: "in_app_chat", label: "In-app Chat", icon: "message" as const },
  { key: "phone", label: "Phone call", icon: "phone" as const },
  { key: "sms", label: "Text message", icon: "sms" as const },
  { key: "whatsapp", label: "WhatsApp", icon: "message" as const },
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
  const { user, logout } = useAuth();
  const { business, setBusiness } = useBusiness();
  const customer = MOCK_CUSTOMERS[0];

  const [fullName, setFullName] = useState(user?.fullName ?? customer.name);
  const [email, setEmail] = useState(user?.email ?? customer.email);
  const [phone, setPhone] = useState(customer.phone);
  const [address, setAddress] = useState(customer.address ?? "");
  const [preferredContact, setPreferredContact] = useState<ContactMethod>("email");
  const [emailQuotes, setEmailQuotes] = useState(true);
  const [smsReminders, setSmsReminders] = useState(true);
  const [saved, setSaved] = useState(false);

  const save = () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <Screen>
      <Header title="Profile" />

      <ScrollView className="flex-1" contentContainerStyle={{ gap: 16, paddingBottom: 40 }}>
        <Text variant="body" color="secondary">
          Your contact details, properties, and preferences for{" "}
          {business?.name ?? "your electrician"}.
        </Text>

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
    </Screen>
  );
}

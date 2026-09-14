import { Linking, View } from "react-native";
import { Button } from "../ui/Button";
import { Text } from "../ui/Text";

export type ContactCustomerCardProps = {
  /** Customer display name (first name is used in the button labels). */
  name: string;
  phone?: string | null;
  email?: string | null;
  /** Customer's preferred contact channel — drives the button order. */
  preferredMethod?: "email" | "phone" | null;
};

/**
 * Shown wherever in-app chat would normally be offered but the customer has no
 * app account (web-form leads): chat is never delivered to them, so follow-ups
 * go by phone or email. The preferred-method-aware primary action comes first.
 */
export function ContactCustomerCard({
  name,
  phone,
  email,
  preferredMethod,
}: ContactCustomerCardProps) {
  const firstName = name.trim().split(/\s+/)[0] || name;

  const call = phone
    ? {
        key: "call" as const,
        testID: "lead-call-button",
        title: `Call ${firstName}`,
        onPress: () => void Linking.openURL(`tel:${phone.replace(/\s+/g, "")}`),
      }
    : null;
  const mail = email
    ? {
        key: "email" as const,
        testID: "lead-email-button",
        title: `Email ${firstName}`,
        onPress: () => void Linking.openURL(`mailto:${email}`),
      }
    : null;

  // Call first by default and for "phone"; email first only for "email".
  const actions =
    preferredMethod === "email"
      ? [mail, call].filter((a) => a !== null)
      : [call, mail].filter((a) => a !== null);

  return (
    <View className="rounded-2xl bg-accent-50 p-4 gap-3">
      <View className="gap-1">
        <Text testID="lead-chat-unavailable" variant="body" weight="semibold">
          This customer doesn't have the app — reach them directly
        </Text>
        <Text variant="caption" color="secondary">
          In-app chat won't reach {firstName}, so follow up by phone or email instead.
        </Text>
      </View>
      {actions.map((action, index) => (
        <Button
          key={action.key}
          testID={action.testID}
          title={action.title}
          variant={index === 0 ? "primary" : "outline"}
          onPress={action.onPress}
        />
      ))}
    </View>
  );
}

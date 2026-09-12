import { useLocalSearchParams, useRouter } from "expo-router";
import { CustomerDetailScreen } from "../../../src/screens/trade/CustomerDetailScreen";
import { useContact } from "../../../src/api/contacts";
import { Header } from "../../../src/components/ui/Header";
import { Screen } from "../../../src/components/ui/Screen";
import { Text } from "../../../src/components/ui/Text";

export default function CustomerDetailRoute() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const { contact, isLoading } = useContact(id);

  if (!contact) {
    return (
      <Screen>
        <Header title="Customer" onBack={() => router.back()} />
        <Text variant="caption" color="secondary" align="center">
          {isLoading ? "Loading customer…" : "This customer could not be loaded."}
        </Text>
      </Screen>
    );
  }

  return (
    <CustomerDetailScreen
      contact={contact}
      onBack={() => router.back()}
      onCreateQuote={() =>
        router.push(
          `/(trade)/quote-intake?contactId=${contact.id}&contactName=${encodeURIComponent(contact.name)}`
        )
      }
    />
  );
}

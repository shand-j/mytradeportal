import { useLocalSearchParams, useRouter } from "expo-router";
import { RequestInfoScreen } from "../../src/screens/trade/RequestInfoScreen";
import { Header } from "../../src/components/ui/Header";
import { Screen } from "../../src/components/ui/Screen";
import { Text } from "../../src/components/ui/Text";
import { useLead } from "../../src/api/quoteRequests";

export default function RequestInfoRoute() {
  const { leadId } = useLocalSearchParams<{ leadId: string }>();
  const router = useRouter();
  const { lead: realLead, isLoading } = useLead(leadId);

  // Never render a blank route: show a loading state while the lead resolves.
  if (!realLead) {
    return (
      <Screen>
        <Header title="In-app chat" onBack={() => router.back()} />
        <Text variant="caption" color="secondary" align="center">
          {isLoading ? "Loading conversation…" : "This lead could not be loaded."}
        </Text>
      </Screen>
    );
  }

  return <RequestInfoScreen lead={realLead} onClose={() => router.back()} />;
}

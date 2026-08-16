import { useLocalSearchParams, useRouter } from "expo-router";
import { RequestInfoScreen } from "../../src/screens/trade/RequestInfoScreen";
import { MOCK_LEADS } from "../../src/data/mockLeads";
import { MOCK_QUOTES } from "../../src/data/mockQuotes";

export default function RequestInfoRoute() {
  const { leadId } = useLocalSearchParams<{ leadId: string }>();
  const router = useRouter();
  const lead = MOCK_LEADS.find((l) => l.id === leadId);

  if (!lead) return null;

  const quote = MOCK_QUOTES.find((q) => q.leadId === lead.id) ?? null;

  return <RequestInfoScreen lead={lead} quote={quote} onClose={() => router.back()} />;
}

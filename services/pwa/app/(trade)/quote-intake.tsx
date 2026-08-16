import { useLocalSearchParams, useRouter } from "expo-router";
import { QuoteIntakeScreen } from "../../src/screens/trade/QuoteIntakeScreen";
import { MOCK_LEADS } from "../../src/data/mockLeads";
import { MOCK_QUOTES } from "../../src/data/mockQuotes";

export default function QuoteIntakeRoute() {
  const { leadId } = useLocalSearchParams<{ leadId: string }>();
  const router = useRouter();
  const lead = MOCK_LEADS.find((l) => l.id === leadId);

  if (!lead) return null;

  const quote = MOCK_QUOTES.find((q) => q.leadId === lead.id) ?? MOCK_QUOTES[0];

  return (
    <QuoteIntakeScreen
      lead={lead}
      onBack={() => router.back()}
      onComplete={() => router.push(`/(trade)/quote/${quote.id}`)}
    />
  );
}

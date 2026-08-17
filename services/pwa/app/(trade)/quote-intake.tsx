import { useLocalSearchParams, useRouter } from "expo-router";
import { QuoteIntakeScreen } from "../../src/screens/trade/QuoteIntakeScreen";
import { MOCK_LEADS } from "../../src/data/mockLeads";
import { MOCK_QUOTES } from "../../src/data/mockQuotes";
import { useLead } from "../../src/api/quoteRequests";
import { generateQuoteFromLead } from "../../src/api/quotes";
import { config } from "../../src/lib/config";

export default function QuoteIntakeRoute() {
  const { leadId } = useLocalSearchParams<{ leadId: string }>();
  const router = useRouter();

  // Connected mode: resolve the real lead; otherwise mock.
  const { lead: realLead } = useLead(leadId);
  const lead = realLead ?? MOCK_LEADS.find((l) => l.id === leadId);

  if (!lead) return null;

  const handleComplete = async () => {
    if (config.apiEnabled && realLead) {
      // Real AI generation from the lead (retrieval + LLM + catalogue pricing).
      // Throws if AI isn't configured; QuoteIntakeScreen surfaces the error.
      const quote = await generateQuoteFromLead(realLead.id);
      router.replace(`/(trade)/quote/${quote.id}`);
      return;
    }
    // Demo: navigate to the mock quote for this lead.
    const quote = MOCK_QUOTES.find((q) => q.leadId === lead.id) ?? MOCK_QUOTES[0];
    router.push(`/(trade)/quote/${quote.id}`);
  };

  return <QuoteIntakeScreen lead={lead} onBack={() => router.back()} onComplete={handleComplete} />;
}

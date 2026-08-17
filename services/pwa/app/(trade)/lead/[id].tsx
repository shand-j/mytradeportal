import { useLocalSearchParams, useRouter } from "expo-router";
import { LeadDetailScreen } from "../../../src/screens/trade/LeadDetailScreen";
import { MOCK_LEADS } from "../../../src/data/mockLeads";
import { useLead } from "../../../src/api/quoteRequests";

export default function LeadDetailRoute() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();

  // Connected mode: resolve the real lead (quote request); otherwise mock.
  const { lead: realLead } = useLead(id);
  const lead = realLead ?? MOCK_LEADS.find((l) => l.id === id);

  if (!lead) return null;

  return (
    <LeadDetailScreen
      lead={lead}
      onBack={() => router.back()}
      onGenerateQuote={() => router.push(`/(trade)/quote-intake?leadId=${lead.id}`)}
      onRequestSiteVisit={() => router.push(`/(trade)/request-info?leadId=${lead.id}`)}
      onMarkDead={() => {
        const idx = MOCK_LEADS.findIndex((l) => l.id === lead.id);
        if (idx !== -1) MOCK_LEADS.splice(idx, 1);
        router.back();
      }}
    />
  );
}

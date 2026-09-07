import { useLocalSearchParams, useRouter } from "expo-router";
import { LeadDetailScreen } from "../../../src/screens/trade/LeadDetailScreen";
import { useLead } from "../../../src/api/quoteRequests";

export default function LeadDetailRoute() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();

  const { lead: realLead } = useLead(id);

  if (!realLead) return null;

  return (
    <LeadDetailScreen
      lead={realLead}
      onBack={() => router.back()}
      onGenerateQuote={() => router.push(`/(trade)/quote-intake?leadId=${realLead.id}`)}
      onRequestSiteVisit={() => router.push(`/(trade)/request-info?leadId=${realLead.id}`)}
      onOpenChat={(l) => router.push(`/(trade)/messages?quoteRequestId=${l.id}`)}
      onMarkDead={() => router.back()}
    />
  );
}

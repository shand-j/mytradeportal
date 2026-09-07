import { useLocalSearchParams, useRouter } from "expo-router";
import { QuoteIntakeScreen, QuoteIntakeData } from "../../src/screens/trade/QuoteIntakeScreen";
import { Header } from "../../src/components/ui/Header";
import { Screen } from "../../src/components/ui/Screen";
import { Text } from "../../src/components/ui/Text";
import { useLead, updateLead } from "../../src/api/quoteRequests";
import { generateQuoteAsync } from "../../src/api/quotes";
import { useQuoteGenerationStore } from "../../src/stores/quoteGenerationStore";

/** Drop blank values so unset intake fields are omitted from the payload. */
function compact(fields: Record<string, string | undefined>): Record<string, string> {
  return Object.fromEntries(
    Object.entries(fields).filter(([, v]) => typeof v === "string" && v.trim() !== "")
  ) as Record<string, string>;
}

export default function QuoteIntakeRoute() {
  const { leadId, contactId, contactName } = useLocalSearchParams<{
    leadId: string;
    contactId: string;
    contactName: string;
  }>();
  const router = useRouter();
  const startGeneration = useQuoteGenerationStore((s) => s.start);

  const { lead: realLead, isLoading } = useLead(leadId);

  // Lead-less mode: create a quote straight from a job description (optionally
  // attached to an existing CRM contact via contactId/contactName params).
  if (!leadId) {
    const contact = contactId
      ? { id: contactId, name: contactName ?? "" }
      : undefined;

    const handleComplete = async (intake: QuoteIntakeData) => {
      const survey = compact({
        propertyType: intake.propertyType,
        bedrooms: intake.bedrooms,
        cuLocation: intake.cuLocation,
        parking: intake.parking,
        access: intake.access,
        electricianNotes: intake.notes,
      });
      await generateQuoteAsync({
        description: intake.description ?? "",
        customerName: intake.customerName || undefined,
        contactId: intake.contactId,
        propertyType: intake.propertyType || undefined,
        siteSurvey: Object.keys(survey).length > 0 ? survey : undefined,
      });
      startGeneration();
      router.replace("/(trade)/quotes");
    };

    return (
      <QuoteIntakeScreen contact={contact} onBack={() => router.back()} onComplete={handleComplete} />
    );
  }

  if (!realLead) {
    // Never render a blank route: show a loading state while the lead resolves.
    return (
      <Screen>
        <Header title="Quote intake" onBack={() => router.back()} />
        <Text variant="caption" color="secondary" align="center">
          {isLoading ? "Loading lead…" : "This lead could not be loaded."}
        </Text>
      </Screen>
    );
  }

  const handleComplete = async (intake: QuoteIntakeData) => {
    const captured = (realLead.structuredData as Record<string, unknown> | undefined) ?? {};

    // Persist the tradesperson's review to the lead before generating the quote.
    const electricianIntake = compact({
      propertyType: intake.propertyType,
      bedrooms: intake.bedrooms,
      cuLocation: intake.cuLocation,
      parking: intake.parking,
      access: intake.access,
      notes: intake.notes,
    });
    await updateLead(realLead.id, {
      structuredData: {
        ...captured,
        electricianIntake,
      },
    });

    await generateQuoteAsync({
      quoteRequestId: realLead.id,
      description: intake.notes,
      propertyType: intake.propertyType || undefined,
      siteSurvey: {
        ...captured,
        ...electricianIntake,
        ...(intake.notes ? { electricianNotes: intake.notes } : {}),
      },
    });
    startGeneration();
    router.replace("/(trade)/quotes");
  };

  return <QuoteIntakeScreen lead={realLead} onBack={() => router.back()} onComplete={handleComplete} />;
}

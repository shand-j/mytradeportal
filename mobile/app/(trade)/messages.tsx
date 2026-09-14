import { useLocalSearchParams, useRouter } from "expo-router";
import { MessagesScreen } from "../../src/screens/customer/MessagesScreen";
import { useLead } from "../../src/api/quoteRequests";

export default function TradeMessagesRoute() {
  const params = useLocalSearchParams();
  const router = useRouter();
  const quoteRequestId = typeof params.quoteRequestId === "string" ? params.quoteRequestId : undefined;

  // Gate the composer for customers who can't receive in-app chat (web-form
  // leads without an app account): the thread still opens, but the composer is
  // replaced with a phone/email contact card.
  const { lead } = useLead(quoteRequestId);
  const unreachableCustomer =
    lead && lead.customerReachable === false
      ? {
          name: lead.customerName,
          phone: lead.customerPhone ?? null,
          email: lead.customerEmail ?? null,
          preferredMethod: lead.contactPreferredMethod ?? null,
        }
      : undefined;

  const handleBack = () => {
    if (router.canGoBack()) {
      router.back();
    } else {
      router.replace("/(trade)/inbox");
    }
  };

  return (
    <MessagesScreen
      quoteRequestId={quoteRequestId}
      senderRole="business"
      initialComposerText={
        typeof params.initialText === "string" ? params.initialText : undefined
      }
      unreachableCustomer={unreachableCustomer}
      onBack={handleBack}
    />
  );
}

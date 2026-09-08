import { useLocalSearchParams, useRouter } from "expo-router";
import { MessagesScreen } from "../../src/screens/customer/MessagesScreen";

export default function TradeMessagesRoute() {
  const params = useLocalSearchParams();
  const router = useRouter();
  const quoteRequestId = typeof params.quoteRequestId === "string" ? params.quoteRequestId : undefined;

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
      onBack={handleBack}
    />
  );
}
